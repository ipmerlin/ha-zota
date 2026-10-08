"""Schedule preview/save and on-demand archive as HA actions with responses."""

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCOUNT_TOKEN, CONF_ALLOW_HTTP, CONF_API_URL, DOMAIN
from .history import get_history
from .protocol import ZotaAuthError, ZotaError

BASE = {vol.Required("entry_id"): str}
CHANGES = {**BASE, vol.Required("changes"): vol.All(list, vol.Length(min=1, max=16))}


def register_services(hass):
    async def handle(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not getattr(entry, "runtime_data", None):
            raise HomeAssistantError("Select a loaded ZOTA integration entry")
        coordinator = entry.runtime_data
        try:
            if call.service == "get_history":
                token = entry.data.get(CONF_ACCOUNT_TOKEN)
                if not token:
                    raise HomeAssistantError("Для архива выполните «Перенастроить» в меню интеграции ZOTA")
                try:
                    return await get_history(
                        async_get_clientsession(hass), entry.data[CONF_API_URL], token,
                        entry.data[CONF_ALLOW_HTTP], coordinator.client.boiler.serial,
                        call.data["start"], call.data["end"],
                        coordinator.data.stages[:coordinator.data.steps + 1],
                    )
                except ZotaAuthError as err:
                    raise HomeAssistantError("Срок входа в архив ZOTA истёк; выполните «Перенастроить»") from err
            result = await coordinator.client.schedule(
                call.data.get("changes"), call.data.get("expected_revision"), call.service == "save_schedule")
            if call.service == "save_schedule":
                await coordinator.async_request_refresh()
            return result if call.return_response else None
        except ZotaError as err:
            raise HomeAssistantError(str(err)) from err

    services = {
        "get_schedule": (BASE, SupportsResponse.ONLY),
        "preview_schedule": (CHANGES, SupportsResponse.ONLY),
        "save_schedule": ({**CHANGES, vol.Required("expected_revision"): vol.Match(r"^[a-f0-9]{64}$")},
                          SupportsResponse.OPTIONAL),
        "get_history": ({**BASE, vol.Required("start"): str, vol.Required("end"): str}, SupportsResponse.ONLY),
    }
    for name, (schema, response) in services.items():
        hass.services.async_register(DOMAIN, name, handle, schema=vol.Schema(schema), supports_response=response)
