"""Discrete power stages, pump mode and thermostat source."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .const import PUMP_MODES, THERMOSTAT_TYPES
from .entity import ZotaEntity
from .settings import SELECTS

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ZotaPower(coordinator),
            ZotaMode(coordinator, "pump_mode", PUMP_MODES),
            ZotaMode(coordinator, "thermostat_type", THERMOSTAT_TYPES),
        ] + [ZotaMode(coordinator, key, spec[1]) for key, spec in SELECTS.items()]
    )


class ZotaPower(ZotaEntity, SelectEntity):
    _attr_translation_key = "power_stage"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator):
        super().__init__(coordinator, "power_stage")

    @property
    def options(self):
        state = self.coordinator.data
        return ["off"] + [f"{i}: {state.stages[i]:g} kW" for i in range(state.steps + 1)]

    @property
    def current_option(self):
        index = self.coordinator.data.power_stage
        return self.options[index + 1] if -1 <= index <= self.coordinator.data.steps else None

    async def async_select_option(self, option):
        await self.coordinator.async_set("power_stage", self.options.index(option) - 1)


class ZotaMode(ZotaEntity, SelectEntity):
    def __init__(self, coordinator, key, options):
        super().__init__(coordinator, key)
        self._key = key
        self._options = options
        self._attr_translation_key = key
        self._attr_options = list(options)
        if key in SELECTS:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def current_option(self):
        state = self.coordinator.data
        value = state.pump_mode if self._key == "pump_mode" else state.values()[self._key]
        return next((k for k, v in self._options.items() if v == value), None)

    async def async_select_option(self, option):
        await self.coordinator.async_set(self._key, self._options[option])
