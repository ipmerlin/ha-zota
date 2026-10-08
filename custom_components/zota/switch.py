"""Boiler power and weather regulation."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .entity import ZotaEntity
from .settings import SWITCHES

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ZotaSwitch(entry.runtime_data, key) for key in ("enabled", "weather_enabled", *SWITCHES)])


class ZotaSwitch(ZotaEntity, SwitchEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._key = key
        self._attr_translation_key = key
        self._attr_icon = "mdi:power" if key == "enabled" else "mdi:weather-partly-cloudy"
        if key in SWITCHES:
            self._attr_entity_category = EntityCategory.CONFIG
        if key == "pressure_protection":
            self._attr_entity_registry_enabled_default = False

    @property
    def is_on(self):
        if self._key in SWITCHES:
            return self.coordinator.data.values()[self._key]
        return getattr(self.coordinator.data, self._key)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set(self._key, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set(self._key, False)
