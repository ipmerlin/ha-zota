"""Pump output and controller fault indicators."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import ZotaEntity
from .protocol import fault_details

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            ZotaBinarySensor(entry.runtime_data, key)
            for key in ("pump_status", "external_off", "errors", "warnings", "antilegionella_active",
                        "thermostat_active", "valve_open_output", "valve_close_output")
        ]
    )


class ZotaBinarySensor(ZotaEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._key = key
        self._attr_translation_key = key
        if key in ("errors", "warnings"):
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self):
        return bool(self.coordinator.data.values()[self._key])

    @property
    def extra_state_attributes(self):
        if self._key in ("errors", "warnings"):
            code = self.coordinator.data.values()[self._key]
            return {"code": code, **fault_details(code, self._key == "warnings")}
        return None
