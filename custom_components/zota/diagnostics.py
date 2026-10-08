"""Diagnostics contain telemetry only, never credentials or account data."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "model": "MK-X",
        "last_update_success": coordinator.last_update_success,
        "poll_interval_seconds": coordinator.update_interval.total_seconds(),
        "values": coordinator.data.values() if coordinator.data else None,
    }
