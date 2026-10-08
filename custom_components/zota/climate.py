"""Room thermostat, backed by the MK-X room sensor and air setpoint."""

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .entity import ZotaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ZotaClimate(entry.runtime_data)])


class ZotaClimate(ZotaEntity, ClimateEntity):
    _attr_translation_key = "room"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 2
    _attr_max_temp = 35
    _attr_target_temperature_step = 0.1
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator):
        super().__init__(coordinator, "room")

    @property
    def current_temperature(self):
        return self.coordinator.data.temperatures[2]

    @property
    def target_temperature(self):
        return self.coordinator.data.air_target

    @property
    def hvac_mode(self):
        return HVACMode.HEAT if self.coordinator.data.enabled else HVACMode.OFF

    @property
    def hvac_action(self):
        state = self.coordinator.data
        if not state.enabled:
            return HVACAction.OFF
        return HVACAction.HEATING if state.raw[1] else HVACAction.IDLE

    async def async_set_temperature(self, **kwargs):
        if ATTR_TEMPERATURE in kwargs:
            await self.coordinator.async_set("air_target", kwargs[ATTR_TEMPERATURE])
        if "hvac_mode" in kwargs:
            await self.async_set_hvac_mode(kwargs["hvac_mode"])

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self.hvac_modes:
            raise ValueError("Unsupported HVAC mode")
        await self.coordinator.async_set("enabled", hvac_mode == HVACMode.HEAT)

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
