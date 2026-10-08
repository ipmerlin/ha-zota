"""ZOTA MK-X integration."""

from homeassistant.const import Platform

from .api import Boiler, ZotaClient
from .const import CONF_BOILER
from .coordinator import ZotaCoordinator

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup_entry(hass, entry):
    data = entry.data[CONF_BOILER]
    client = ZotaClient(Boiler(data["serial"], data["name"], data["server"], data["password"]))
    coordinator = ZotaCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def _async_update_options(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
