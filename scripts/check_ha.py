"""Smoke-check entity API compatibility with real Home Assistant."""

import asyncio
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


asyncio.run(check_climate_services())
print("Home Assistant module imports and entity API smoke checks passed")
