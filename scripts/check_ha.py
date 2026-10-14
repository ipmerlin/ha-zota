"""Smoke-check entity API compatibility with real Home Assistant."""

import asyncio
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.zota.api import Boiler  # noqa: E402
from custom_components.zota.protocol import BoilerState, parse_info, parse_program  # noqa: E402

for name in (
    "__init__",
    "config_flow",
    "climate",
    "sensor",
    "binary_sensor",
    "number",
    "select",
    "switch",
    "diagnostics",
    "services",
):
    import_module(f"custom_components.zota.{name}")

# Import test telemetry without installing a fake HA package or executing tests.
namespace = {}
source = (Path(__file__).resolve().parents[1] / "tests/conftest.py").read_text()
exec(source[source.index("CAPTURE =") :], namespace)
from dataclasses import replace  # noqa: E402

state = replace(BoilerState.parse(namespace["CAPTURE"]), details={
    **parse_info(bytes.fromhex("5a001c10")),
    **parse_program(bytes.fromhex("030100")),
})
coordinator = SimpleNamespace(
    data=state,
    client=SimpleNamespace(boiler=Boiler(1234, "Test", "unused.invalid", 0)),
    last_update_success=True,
)
climate = import_module("custom_components.zota.climate").ZotaClimate(coordinator)
assert climate.hvac_mode.value == "heat"
assert climate.current_temperature == 17.4
assert climate.target_temperature == 18
water = import_module("custom_components.zota.number").ZotaWaterTarget(coordinator)
assert (water.native_min_value, water.native_max_value, water.native_value) == (50, 80, 72)
power = import_module("custom_components.zota.select").ZotaPower(coordinator)
assert power.current_option == "3: 4.5 kW"
assert len(power.options) == 8


async def check_climate_services():
    coordinator.async_set = AsyncMock()
    await climate.async_set_temperature(temperature=21.5, hvac_mode="heat")
    assert coordinator.async_set.await_args_list[0].args == ("air_target", 21.5)
    assert coordinator.async_set.await_args_list[1].args == ("enabled", True)
    # Exercise all newly constructed entity properties with the real HA API.
    import json

    translations = json.loads((Path(__file__).resolve().parents[1] /
                               "custom_components/zota/translations/ru.json").read_text(encoding="utf-8"))
    all_entities = []
    for platform in ("number", "select", "switch", "sensor", "binary_sensor"):
        entities = []
        await import_module(f"custom_components.zota.{platform}").async_setup_entry(
            None, SimpleNamespace(runtime_data=coordinator), entities.extend)
        for entity in entities:
            assert entity.translation_key in translations["entity"][platform]
            assert entity.device_info["sw_version"] == "1.12"
            if platform == "number":
                assert entity.native_min_value <= entity.native_max_value
                entity.native_value
            elif platform == "select":
                assert entity.current_option is None or entity.current_option in entity.options
            elif platform in ("switch", "binary_sensor"):
                assert isinstance(entity.is_on, bool)
            else:
                entity.native_value
            if hasattr(entity, "extra_state_attributes"):
                entity.extra_state_attributes
        all_entities.extend(entities)
    assert len({entity.unique_id for entity in all_entities}) == len(all_entities)
    print("Checked entity properties:", len(all_entities))
    from homeassistant.core import HomeAssistant

    from custom_components.zota.services import register_services

    hass = HomeAssistant(str(Path.cwd()))
    register_services(hass)
    for service in ("get_schedule", "preview_schedule", "save_schedule", "get_history"):
        assert hass.services.has_service("zota", service)
    fake_entry = SimpleNamespace(domain="zota", runtime_data=coordinator, data={})
    hass.config_entries = SimpleNamespace(async_get_entry=lambda entry_id: fake_entry)
    coordinator.client.schedule = AsyncMock(return_value={"revision": "test", "confirmed": True})
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_refresh_after_command = AsyncMock()
    response = await hass.services.async_call("zota", "get_schedule", {"entry_id": "test"},
                                             blocking=True, return_response=True)
    assert response["revision"] == "test"
    changes = [{"period_index": 0, "air_target": 22.1}]
    await hass.services.async_call("zota", "preview_schedule", {"entry_id": "test", "changes": changes},
                                   blocking=True, return_response=True)
    assert coordinator.client.schedule.await_args.args == (changes, None, False)
    await hass.services.async_call("zota", "save_schedule", {
        "entry_id": "test", "changes": changes, "expected_revision": "0" * 64}, blocking=True)
    assert coordinator.client.schedule.await_args.args == (changes, "0" * 64, True)
    coordinator.async_refresh_after_command.assert_awaited_once()
    await check_post_command_refresh(hass)
    await check_read_recovery(hass)
    await check_configuration_paths(hass)


async def check_read_recovery(hass):
    from homeassistant.exceptions import ConfigEntryAuthFailed
    from homeassistant.helpers.update_coordinator import UpdateFailed

    module = import_module("custom_components.zota.coordinator")
    protocol = import_module("custom_components.zota.protocol")
    client = SimpleNamespace(fetch=AsyncMock())
    control = module.ZotaCoordinator(hass, SimpleNamespace(options={}, async_on_unload=Mock()), client)
    control.data = state
    fresh = replace(state, details={})
    client.fetch.side_effect = [protocol.ZotaConnectionError("Timed out"), fresh]
    with patch.object(module.asyncio, "sleep", AsyncMock()) as sleep:
        result = await control._async_update_data()
        assert result.raw == fresh.raw and result.details == state.details
        assert client.fetch.await_count == 2
        sleep.assert_awaited_once_with(2)

        for error, expected, attempts in (
            (protocol.ZotaConnectionError("Offline"), UpdateFailed, 2),
            (protocol.ZotaAuthError("Rejected"), ConfigEntryAuthFailed, 1),
            (protocol.ZotaError("Invalid packet"), UpdateFailed, 1),
        ):
            client.fetch.reset_mock()
            client.fetch.side_effect = error
            try:
                await control._async_update_data()
            except expected:
                pass
            else:
                raise AssertionError("Persistent failure must not return cached telemetry")
            assert client.fetch.await_count == attempts
    print("Transient read recovery, metadata preservation and persistent outage checks passed")


async def check_post_command_refresh(hass):
    module = import_module("custom_components.zota.coordinator")
    client = SimpleNamespace(set=AsyncMock(return_value=state))
    entry = SimpleNamespace(options={}, async_on_unload=Mock())
    control = module.ZotaCoordinator(hass, entry, client)
    control.async_refresh = AsyncMock()
    control.async_set_updated_data = Mock()
    control.async_set_update_error = Mock()
    timers = []

    def schedule(hass, delay, callback):
        cancel = Mock()
        timers.append((delay, callback, cancel))
        return cancel

    with patch.object(module, "async_call_later", side_effect=schedule):
        await control.async_set("air_target", 26.5)
        client.set.assert_awaited_once_with("air_target", 26.5)
        control.async_set_updated_data.assert_called_once()
        control.async_refresh.assert_awaited_once()
        assert [delay for delay, _, _ in timers] == [10, 30]
        for _, callback, _ in timers:
            await callback(None)
        assert control.async_refresh.await_count == 3
        assert client.set.await_count == 1

        old_timers = list(timers)
        await control.async_refresh_after_command()
        for _, _, cancel in old_timers:
            cancel.assert_called_once()
        count = control.async_refresh.await_count
        await old_timers[0][1](None)
        assert control.async_refresh.await_count == count
        control.async_cancel_post_command_refresh()
        for _, callback, cancel in timers[2:]:
            cancel.assert_called_once()
            await callback(None)
        assert control.async_refresh.await_count == count
        assert not control._post_command_refresh_cancels

        # Unloading or a newer command during a read must not recreate timers.
        control.async_refresh = AsyncMock(side_effect=control.async_cancel_post_command_refresh)
        timer_count = len(timers)
        await control.async_refresh_after_command()
        assert len(timers) == timer_count
    print("Post-command reads, replacement and unload cleanup passed")

    from homeassistant.exceptions import HomeAssistantError

    control.async_refresh = AsyncMock()
    client.set.side_effect = module.ZotaError("Command not confirmed")
    try:
        await control.async_set("air_target", 26.5)
    except HomeAssistantError:
        pass
    else:
        raise AssertionError("Failed command must still be reported")
    control.async_set_update_error.assert_not_called()
    control.async_refresh.assert_awaited_once()


async def check_configuration_paths(hass):
    from homeassistant import config_entries

    from custom_components.zota.protocol import ZotaError

    module = import_module("custom_components.zota.config_flow")
    boiler = Boiler(1234, "Test", "unused.invalid", 0)
    entry = SimpleNamespace(data={"boiler": boiler.as_config()})
    account = SimpleNamespace(boilers=AsyncMock(return_value=[boiler]), token="fresh-token")
    user_input = {"username": "test-user", "password": "test-password",
                  "api_url": "http://control.zota.ru:81", "allow_http": True}
    with patch.object(module, "ZotaAccount", return_value=account), \
         patch.object(module, "async_get_clientsession", return_value=None), \
         patch.object(module.ZotaClient, "fetch", AsyncMock(side_effect=ZotaError("TCP unavailable"))) as fetch:
        flow = module.ZotaConfigFlow()
        flow.hass = hass
        flow.context = {"source": config_entries.SOURCE_RECONFIGURE}
        flow._get_reconfigure_entry = lambda: entry
        flow.async_update_reload_and_abort = lambda entry, **kwargs: {"type": "abort", **kwargs}
        flow.async_show_form = lambda **kwargs: kwargs
        result = await flow.async_step_user(user_input)
        assert result["type"] == "abort" and result["data_updates"]["account_token"] == "fresh-token"
        assert "password" not in result["data_updates"]
        fetch.assert_not_awaited()

        flow.context = {"source": config_entries.SOURCE_REAUTH}
        flow._get_reauth_entry = lambda: entry
        result = await flow.async_step_user(user_input)
        assert result["errors"] == {"base": "boiler_connect"}

        account.boilers.side_effect = ZotaError("API unavailable")
        flow.context = {"source": config_entries.SOURCE_RECONFIGURE}
        result = await flow.async_step_user(user_input)
        assert result["errors"] == {"base": "account_connect"}


asyncio.run(check_climate_services())
print("Home Assistant module imports and entity API smoke checks passed")
