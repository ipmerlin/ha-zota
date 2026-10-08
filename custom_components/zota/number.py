"""Water temperature setpoint with limits read from the boiler."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature

from .entity import ZotaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ZotaWaterTarget(entry.runtime_data)])


class ZotaWaterTarget(ZotaEntity, NumberEntity):
    _attr_translation_key = "water_target"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(self, coordinator):
        super().__init__(coordinator, "water_target_control")

    @property
    def native_value(self):
        return self.coordinator.data.water_target

    @property
    def native_min_value(self):
        return self.coordinator.data.water_min

    @property
    def native_max_value(self):
        return self.coordinator.data.water_max

    async def async_set_native_value(self, value):
        await self.coordinator.async_set("water_target", value)
