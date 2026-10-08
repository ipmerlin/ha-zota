"""MK-X wire protocol, independently implemented from ZOTA Net 2.11.3.

Frames: little endian uint16 link type, opcode, payload length.
Data version 1 has exactly 102 bytes. Preserve settings blocks byte for byte.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from .settings import NUMBERS, SETTINGS, SWITCHES, read_setting, setting_limits


class ZotaError(Exception):
    """A transport, protocol or rejected command error."""


class ZotaAuthError(ZotaError):
    """Account or boiler authentication failed."""


def frame(link: int, opcode: int, payload: bytes) -> bytes:
    """Build a frame with a payload length, not total frame length."""
    if len(payload) > 4096:
        raise ZotaError("Oversized frame")
    return struct.pack("<HHH", link, opcode, len(payload)) + payload


def auth_frame(serial: int, password: int) -> bytes:
    return frame(0, 0, struct.pack("<HHII", 0, 24, serial, password))


def command_frame(command: int, payload: bytes = b"") -> bytes:
    return frame(1, 0, struct.pack("<H", command) + payload)


def temperature(raw: int, divisor: int = 1) -> float | None:
    # 0x4000 and above denote short circuit / disconnected / sensor error.
    return raw / divisor if raw < 0x4000 else None


def parse_info(raw: bytes) -> dict:
    if len(raw) != 4:
        raise ZotaError("Unsupported MK-X info length")
    power, firmware, indicator = struct.unpack("<HBB", raw)
    return {"nominal_power": power / 10,
            "firmware": f"{firmware >> 4}.{firmware & 15}",
            "indicator_firmware": f"{indicator >> 4}.{indicator & 15}"}


def parse_program(raw: bytes) -> dict:
    """Read the returned program without assuming inactive programs are included."""
    if len(raw) < 2 or raw[0] != 3 or raw[1] not in range(1, 6):
        raise ZotaError("Unsupported MK-X thermostat program")
    mode = raw[1]
    if mode == 5:
        if len(raw) not in (3, 4):
            raise ZotaError("Invalid party program length")
        return {"program_mode": mode, "program_days": raw[-1], "program_periods": []}
    programs = 2 if mode == 3 else 1
    offset, periods = 2, []
    for index in range(programs):
        if offset >= len(raw) or raw[offset] > 8:
            raise ZotaError("Invalid thermostat period count")
        count = raw[offset]
        offset += 1
        for _ in range(count):
            if offset + 8 > len(raw):
                raise ZotaError("Truncated thermostat period")
            begin, end, flags, dhw, air, water, power = struct.unpack_from("<BBBBhBB", raw, offset)
            periods.append({"program_index": index, "begin": begin, "end": end,
                            "flags": flags, "dhw_target": dhw, "air_target": air / 10,
                            "water_target": water, "power_stage": power})
            offset += 8
    if offset != len(raw):
        raise ZotaError("Unexpected thermostat program bytes")
    return {"program_mode": mode, "program_periods": periods}


FAULT_BITS = {1: "critical_overheat", 2: "overheat", 3: "relay_fuse", 4: "fuse",
              5: "high_pressure", 6: "low_pressure", 7: "ssr_overheat",
              8: "phase_control", 9: "main_power_off"}
WARNING_BITS = {1: "high_pressure", 2: "low_pressure", 3: "low_water_temperature", 14: "relay_wear"}


def fault_details(code: int, warning: bool = False) -> dict:
    bits = WARNING_BITS if warning else FAULT_BITS
    names = [name for bit, name in bits.items() if code & (1 << bit)]
    sensors = ({"room": 4, "dhw": 6, "outside": 8, "ssr": 10, "aux": 12}
               if warning else {"water": 10, "pressure": 12})
    sensor_errors = {name: (code >> shift) & 3 for name, shift in sensors.items() if (code >> shift) & 3}
    return {"active_faults": names, "sensor_error_codes": sensor_errors}


@dataclass(frozen=True)
class BoilerState:
    """Validated data and original settings blocks."""

    raw: bytes
    details: dict | None = None

    @classmethod
    def parse(cls, raw: bytes) -> BoilerState:
        if len(raw) != 102 or raw[0] != 1:
            raise ZotaError("Unsupported MK-X data version or length")
        state = cls(raw)
        if not 1 <= state.steps <= 9 or state.raw[1] > state.steps:
            raise ZotaError("Invalid power stage data")
        if not 20 <= raw[37] <= raw[36] <= 90:
            raise ZotaError("Invalid water temperature limits")
        if not -1 <= state.power_stage <= state.steps:
            raise ZotaError("Invalid power setting")
        if any(v <= 0 for v in state.stages[1 : state.steps + 1]):
            raise ZotaError("Invalid power stage table")
        return state

    @property
    def steps(self) -> int:
        return self.raw[2]

    @property
    def stages(self) -> tuple[float, ...]:
        return (0.0,) + tuple(v / 10 for v in struct.unpack_from("<9h", self.raw, 12))

    @property
    def power_stage(self) -> int:
        return struct.unpack_from("<b", self.raw, 49)[0]

    @property
    def air_target(self) -> float:
        return struct.unpack_from("<h", self.raw, 30)[0] / 10

    @property
    def water_target(self) -> int:
        return self.raw[35]

    @property
    def water_min(self) -> int:
        return self.raw[37]

    @property
    def water_max(self) -> int:
        return self.raw[36]

    @property
    def temperatures(self) -> tuple[float | None, ...]:
        values = struct.unpack_from("<6h", self.raw, 68)
        return tuple(temperature(v, 10 if i == 2 else 1) for i, v in enumerate(values))

    @property
    def state_bits(self) -> int:
        return struct.unpack_from("<H", self.raw, 84)[0]

    @property
    def enabled(self) -> bool:
        # XBoiler.startStop sends ON=1 when currently in standby.
        return not bool(self.state_bits & 16)

    @property
    def pump_mode(self) -> int:
        return (struct.unpack_from("<H", self.raw, 55)[0] >> 3) & 3

    @property
    def weather_enabled(self) -> bool:
        return bool(self.raw[50] & 1)

    def values(self) -> dict:
        temps = self.temperatures
        pressure = struct.unpack_from("<h", self.raw, 8)[0]
        return {
            "actual_temp": temps[0],
            "outside_temp": temps[1],
            "air_temp": temps[2],
            "dhw_temp": temps[3],
            "air_target": self.air_target,
            "water_target": self.water_target,
            "calculated_target": self.raw[3],
            "actual_power": self.stages[self.raw[1]],
            "target_power": self.stages[self.power_stage] if 0 <= self.power_stage <= self.steps else None,
            "pressure": pressure / 1000 if 0 <= pressure < 0x4000 else None,
            "pump_status": bool(struct.unpack_from("<H", self.raw, 86)[0] & 4),
            "circuit_mode": struct.unpack_from("<H", self.raw, 55)[0] & 7,
            "operation_mode": self.state_bits & 3,
            "external_off": bool(self.state_bits & 8),
            "errors": struct.unpack_from("<I", self.raw, 88)[0],
            "warnings": struct.unpack_from("<I", self.raw, 92)[0],
            "thermostat_type": self.raw[11],
            "aux_temp": temps[5],
            "ssr_temp": temps[4],
            "scheme": struct.unpack_from("<H", self.raw, 4)[0],
            "weather_target": self.raw[6],
            "gsm_signal": self.raw[7],
            "dhw_state": self.raw[10],
            "thermostat_program": self.raw[59],
            "thermostat_active": bool(self.raw[60] & 1),
            "antilegionella_active": bool(self.state_bits & 4),
            "valve_open_output": bool(self.raw[86] & 1),
            "valve_close_output": bool(self.raw[86] & 2),
            "sensor_roles": tuple((struct.unpack_from("<I", self.raw, 80)[0] >> (4 * i)) & 15
                                  for i in range(6)),
            "controller_time": "%04d-%02d-%02d %02d:%02d:%02d" % (
                2000 + self.raw[101], self.raw[100], self.raw[99], self.raw[98], self.raw[97], self.raw[96]),
            **{key: read_setting(self.raw, key) for key in SETTINGS},
            **(self.details or {}),
        }


def _scaled(value: float, low: float, high: float, scale: int = 1) -> int:
    if isinstance(value, bool) or not math.isfinite(value) or not low <= value <= high:
        raise ZotaError("Value outside permitted range")
    scaled = value * scale
    if not math.isclose(scaled, round(scaled), abs_tol=1e-7):
        raise ZotaError("Value does not match the permitted step")
    return round(scaled)


def setting_command(state: BoilerState, key: str, value) -> tuple[int, bytes]:
    """Modify one setting while preserving all other bytes in its block."""
    raw = state.raw
    if key in SETTINGS:
        spec = SETTINGS[key]
        if key in SWITCHES:
            if not isinstance(value, bool):
                raise ZotaError("A boolean value is required")
            scaled = int(value)
        else:
            low, high = setting_limits(raw, key) if key in NUMBERS else (spec.low, spec.high)
            scaled = _scaled(value, low, high, spec.scale)
        block = bytearray(raw[spec.start:spec.end])
        offset = spec.offset - spec.start
        if spec.width:
            size = 2 if spec.end - spec.start == 2 else 1
            bits = int.from_bytes(block[offset:offset + size], "little")
            mask = ((1 << spec.width) - 1) << spec.shift
            block[offset:offset + size] = ((bits & ~mask) | scaled << spec.shift).to_bytes(size, "little")
        else:
            block[offset:offset + 1] = scaled.to_bytes(1, "little", signed=spec.signed)
        # Protect valid relationships even when called outside the HA UI.
        patched = raw[:spec.start] + block + raw[spec.end:]
        if spec.command == 10 and not patched[47] < patched[46] < patched[45] < patched[44] <= 30:
            raise ZotaError("Pressure thresholds must increase strictly")
        if key in ("water_min", "water_max") and not patched[37] <= patched[35] <= patched[36]:
            raise ZotaError("Water limits must include the current setpoint")
        return spec.command, bytes(block)
    if key == "air_target":
        if state.temperatures[2] is None:
            raise ZotaError("Room sensor unavailable")
        return 9, struct.pack("<h", _scaled(value, 2, 35, 10)) + raw[32:35]
    if key == "water_target":
        if state.temperatures[0] is None:
            raise ZotaError("Water sensor unavailable")
        return 7, bytes([_scaled(value, state.water_min, state.water_max)]) + raw[36:39]
    if key == "power_stage":
        return 3, raw[48:49] + struct.pack("<b", _scaled(value, -1, state.steps))
    if key == "pump_mode":
        selected = _scaled(value, 1, 3)
        bits = struct.unpack_from("<H", raw, 55)[0]
        return 14, struct.pack("<H", (bits & ~(3 << 3)) | selected << 3)
    if key in ("enabled", "weather_enabled"):
        if not isinstance(value, bool):
            raise ZotaError("A boolean value is required")
        if key == "enabled":
            return 20, struct.pack("<H", int(value))
        return 13, bytes([(raw[50] & ~1) | int(value)]) + raw[51:55]
    if key == "thermostat_type":
        return 21, struct.pack("<H", _scaled(value, 0, 3))
    raise ZotaError("Unsupported setting")


def setting_matches(state: BoilerState, key: str, value) -> bool:
    """Verify actual readback without optimistic state updates."""
    actual = state.values()[key] if key == "thermostat_type" or key in SETTINGS else getattr(state, key)
    return actual == value
