"""Edit returned MK-X periods, preserving every unselected byte and flag."""

import hashlib
import math
import struct

from .protocol import BoilerState, ZotaError, parse_program

FIELDS = {"begin", "end", "air_target", "water_target", "dhw_target", "power_stage",
          "use_air", "use_water", "use_dhw", "use_power"}


def revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def program_view(raw: bytes) -> dict:
    return {"revision": revision(raw), **parse_program(raw)}


def _integer(value, low, high, scale=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ZotaError("Invalid schedule value")
    scaled = value * scale
    if not low <= value <= high or not math.isclose(scaled, round(scaled), abs_tol=1e-7):
        raise ZotaError("Schedule value outside permitted range or step")
    return round(scaled)


def patch_program(raw: bytes, state: BoilerState, changes: list[dict]) -> bytes:
    """Only existing workday/holiday/automatic periods can be edited.

    Vacation/party use a different structure in read/write paths of ZOTA Net.
    Reject them until their firmware-specific layout has been verified.
    """
    parsed = parse_program(raw)
    if parsed["program_mode"] not in (1, 2, 3) or not changes or len(changes) > 16:
        raise ZotaError("Only existing workday, holiday or automatic periods can be edited")
    offsets, offset = {}, 2
    for program in range(2 if raw[1] == 3 else 1):
        for period in range(raw[offset]):
            offsets[program, period] = offset + 1 + period * 8
        offset += 1 + raw[offset] * 8
    patched, seen = bytearray(raw), set()
    for change in changes:
        if not isinstance(change, dict) or set(change) - FIELDS - {"program_index", "period_index"}:
            raise ZotaError("Unknown schedule field")
        program = _integer(change.get("program_index", 0), 0, 1)
        period = _integer(change.get("period_index"), 0, 7)
        key = program, period
        if key not in offsets or key in seen or not set(change) & FIELDS:
            raise ZotaError("Missing, duplicate or unknown period")
        seen.add(key)
        pos = offsets[key]
        byte_fields = {"begin": (0, 0, 23), "end": (1, 1, 24),
                       "dhw_target": (3, 20, min(70, state.raw[41])),
                       "water_target": (6, state.water_min, state.water_max),
                       "power_stage": (7, 0, state.steps)}
        for name, (index, low, high) in byte_fields.items():
            if name in change:
                patched[pos + index] = _integer(change[name], low, high)
        if "air_target" in change:
            struct.pack_into("<h", patched, pos + 4, _integer(change["air_target"], 2, 35, 10))
        for name, bit in {"use_dhw": 0, "use_air": 1, "use_water": 2, "use_power": 3}.items():
            if name in change:
                if not isinstance(change[name], bool):
                    raise ZotaError("Schedule enable flag must be boolean")
                patched[pos + 2] = (patched[pos + 2] & ~(1 << bit)) | int(change[name]) << bit
    # Preserve period counts and ordering; require a contiguous whole day.
    for program in range(2 if raw[1] == 3 else 1):
        previous = 0
        for key, pos in offsets.items():
            if key[0] != program:
                continue
            begin, end = patched[pos:pos + 2]
            if begin != previous or not begin < end <= 24:
                raise ZotaError("Schedule must cover 00:00–24:00 without gaps or overlaps")
            previous = end
            flags = patched[pos + 2]
            if flags & 1:
                _integer(patched[pos + 3], 20, min(70, state.raw[41]))
            if flags & 2:
                _integer(struct.unpack_from("<h", patched, pos + 4)[0] / 10, 2, 35, 10)
            if flags & 4:
                _integer(patched[pos + 6], state.water_min, state.water_max)
            if flags & 8:
                _integer(patched[pos + 7], 0, state.steps)
        if previous != 24:
            raise ZotaError("Schedule must cover the entire day")
    return bytes(patched)
