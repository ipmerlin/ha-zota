"""MK-X settings described by byte/bit position in telemetry version 1.

Ranges and scales follow the corresponding ZOTA Net settings screens.
The entire original command block is preserved except the selected field.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Setting:
    command: int
    start: int
    end: int
    offset: int
    low: float
    high: float
    scale: int = 1
    signed: bool = False
    shift: int = 0
    width: int = 0
    unit: str | None = None


NUMBERS = {
    "air_hysteresis_upper": Setting(9, 30, 35, 33, 0, 5, 10, unit="°C"),
    "air_hysteresis_lower": Setting(9, 30, 35, 32, 0, 5, 10, unit="°C"),
    "air_correction": Setting(9, 30, 35, 34, -10, 10, signed=True, unit="°C"),
    "water_max": Setting(7, 35, 39, 36, 60, 90, unit="°C"),
    "water_min": Setting(7, 35, 39, 37, 20, 50, unit="°C"),
    "water_low_warning": Setting(7, 35, 39, 38, 0, 90, unit="°C"),
    "dhw_target": Setting(8, 39, 43, 40, 20, 70, signed=True, unit="°C"),
    "dhw_max": Setting(8, 39, 43, 41, 30, 70, unit="°C"),
    "dhw_correction": Setting(8, 39, 43, 42, -10, 10, signed=True, unit="°C"),
    "pressure_max": Setting(10, 43, 48, 44, 0.3, 3, 10, unit="bar"),
    "pressure_high_warning": Setting(10, 43, 48, 45, 0.2, 2.9, 10, unit="bar"),
    "pressure_low_warning": Setting(10, 43, 48, 46, 0.1, 2.8, 10, unit="bar"),
    "pressure_min": Setting(10, 43, 48, 47, 0, 2.7, 10, unit="bar"),
    "weather_coefficient": Setting(13, 50, 55, 51, 0.2, 4.2, 10),
    "outside_correction": Setting(13, 50, 55, 52, -10, 10, signed=True, unit="°C"),
    "summer_threshold": Setting(13, 50, 55, 53, 0, 25, signed=True, unit="°C"),
    "weather_room_target": Setting(13, 50, 55, 54, 10, 30, signed=True, unit="°C"),
    "pump_delay": Setting(14, 55, 57, 55, 1, 120, shift=5, width=8, unit="min"),
    "valve_travel_time": Setting(17, 57, 59, 57, 0, 500, shift=5, width=10, unit="s"),
    "external_water_reduction": Setting(19, 66, 68, 66, 0, 50, shift=9, width=6, unit="°C"),
    "external_power_stage": Setting(19, 66, 68, 66, 0, 9, shift=5, width=4),
}

SWITCHES = {
    "antilegionella_enabled": Setting(8, 39, 43, 39, 0, 1, width=1),
    "pressure_protection": Setting(10, 43, 48, 43, 0, 1, width=1),
    "power_on_delay": Setting(3, 48, 50, 48, 0, 1, shift=1, width=1),
    "auto_winter_summer": Setting(13, 50, 55, 50, 0, 1, shift=1, width=1),
}

SELECTS = {
    "power_accuracy": (Setting(3, 48, 50, 48, 0, 1, width=1), {"coarse": 0, "fine": 1}),
    "pump_circuit": (Setting(14, 55, 57, 55, 1, 5, width=3), {
        "boiler": 1, "heating": 2, "heating_dhw": 3,
        "off_after_water_heating": 4, "off_after_dhw_heating": 5,
    }),
    "valve_type": (Setting(17, 57, 59, 57, 0, 1, width=2), {"none": 0, "switching": 1}),
    "valve_mode": (Setting(17, 57, 59, 57, 0, 3, shift=2, width=3), {
        "none": 0, "dhw_priority": 1, "heating": 2, "dhw": 3,
    }),
    "external_response": (Setting(19, 66, 68, 66, 1, 4, width=3), {
        "boiler_off": 1, "pump_off": 2, "reduce_water": 3, "reduce_power": 4,
    }),
    "external_contact": (Setting(19, 66, 68, 66, 1, 2, shift=3, width=2), {
        "normally_closed": 1, "normally_open": 2,
    }),
}
SETTINGS = {**NUMBERS, **SWITCHES, **{key: item[0] for key, item in SELECTS.items()}}


def read_setting(raw: bytes, key: str):
    spec = SETTINGS[key]
    if spec.width:
        size = 2 if spec.end - spec.start == 2 else 1
        bits = int.from_bytes(raw[spec.offset:spec.offset + size], "little")
        value = (bits >> spec.shift) & ((1 << spec.width) - 1)
    else:
        value = int.from_bytes(raw[spec.offset:spec.offset + 1], "little", signed=spec.signed)
    return bool(value) if key in SWITCHES else value / spec.scale


def setting_limits(raw: bytes, key: str) -> tuple[float, float]:
    spec = NUMBERS[key]
    low, high = spec.low, spec.high
    if key == "dhw_target":
        high = min(high, raw[41])
    elif key == "dhw_max" and raw[40] >= 20:
        low = max(low, raw[40])
    elif key == "water_low_warning":
        high = raw[36]
    elif key == "water_max" and raw[35] >= raw[37]:
        low = max(low, raw[35])
    elif key == "water_min" and raw[35] >= raw[37]:
        high = min(high, raw[35])
    elif key == "external_power_stage":
        high = raw[2]
    elif key == "pressure_max":
        low = (raw[45] + 1) / 10
    elif key == "pressure_high_warning":
        low, high = (raw[46] + 1) / 10, (raw[44] - 1) / 10
    elif key == "pressure_low_warning":
        low, high = (raw[47] + 1) / 10, (raw[45] - 1) / 10
    elif key == "pressure_min":
        high = (raw[46] - 1) / 10
    return max(spec.low, low), min(spec.high, high)
