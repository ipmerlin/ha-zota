"""Boiler power and weather regulation."""

from homeassistant.components.switch import SwitchEntity

from .entity import ZotaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ZotaSwitch(entry.runtime_data, key) for key in ("enabled", "weather_enabled")])


class ZotaSwitch(ZotaEntity, SwitchEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._key = key
        self._attr_translation_key = key
        self._attr_icon = "mdi:power" if key == "enabled" else "mdi:weather-partly-cloudy"

    @property
    def is_on(self):
        return getattr(self.coordinator.data, self._key)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set(self._key, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set(self._key, False)
