"""Device identity shared by all ZOTA entities."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class ZotaEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        boiler = coordinator.client.boiler
        self._attr_unique_id = f"mk_x_{boiler.serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"mk_x_{boiler.serial}")},
            name=boiler.name,
            manufacturer="ZOTA",
            model="MK-X",
            serial_number=str(boiler.serial),
            configuration_url=f"https://control.zota.ru/MK_X/{boiler.serial}",
            sw_version=(coordinator.data.details or {}).get("firmware") if coordinator.data else None,
        )
