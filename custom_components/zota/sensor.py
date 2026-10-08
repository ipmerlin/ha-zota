"""MK-X telemetry."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfPower, UnitOfPressure, UnitOfTemperature

from .entity import ZotaEntity

PARALLEL_UPDATES = 0
SENSORS = {
    "actual_temp": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "air_temp": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "outside_temp": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "dhw_temp": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "air_target": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "water_target": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "calculated_target": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "actual_power": (SensorDeviceClass.POWER, UnitOfPower.KILO_WATT),
    "target_power": (SensorDeviceClass.POWER, UnitOfPower.KILO_WATT),
    "pressure": (SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    "operation_mode": (SensorDeviceClass.ENUM, None),
    "circuit_mode": (None, None),
}
OP_MODES = {0: "work", 1: "stop", 2: "pause", 3: "full_stop"}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ZotaSensor(entry.runtime_data, key, *attrs) for key, attrs in SENSORS.items()])


class ZotaSensor(ZotaEntity, SensorEntity):
    def __init__(self, coordinator, key, device_class, unit):
        super().__init__(coordinator, key)
        self._key = key
        self._attr_translation_key = key
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        if unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key == "operation_mode":
            self._attr_options = list(OP_MODES.values())

    @property
    def native_value(self):
        value = self.coordinator.data.values()[self._key]
        return OP_MODES.get(value) if self._key == "operation_mode" else value
