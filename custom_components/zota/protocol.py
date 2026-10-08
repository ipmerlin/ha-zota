"""MK-X wire protocol, independently implemented from ZOTA Net 2.11.3.

Frames: little endian uint16 link type, opcode, payload length.
Data version 1 has exactly 102 bytes. Preserve settings blocks byte for byte.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


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


@dataclass(frozen=True)
class BoilerState:
    """Validated data and original settings blocks."""

    raw: bytes

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
    actual = state.values()[key] if key == "thermostat_type" else getattr(state, key)
    return actual == value
