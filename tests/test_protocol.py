import math
import struct

import pytest
from conftest import CAPTURE
from zota_wire.protocol import BoilerState, ZotaError, auth_frame, setting_command, temperature


def test_captured_telemetry_units_and_state():
    state = BoilerState.parse(CAPTURE)
    values = state.values()
    assert values["actual_temp"] == 25
    assert values["outside_temp"] == 12
    assert values["air_temp"] == 17.4
    assert values["pressure"] == 0.712
    assert values["actual_power"] == 0
    assert values["target_power"] == 4.5
    assert state.steps == 6
    assert state.enabled is True  # PAUSE is enabled; standby is false.
    assert values["operation_mode"] == 2
    assert values["dhw_temp"] is None
    assert state.air_target == 18


@pytest.mark.parametrize("code", [0x4000, 0x4001, 0x4002, 0x4003])
def test_sensor_error_codes_are_unknown(code):
    assert temperature(code) is None
    assert temperature(code, 10) is None
    assert temperature(-125, 10) == -12.5


@pytest.mark.parametrize(
    "key,value,cmd,offset,length,expected",
    [
        ("air_target", 21.5, 9, 30, 5, b"\xd7\x00"),
        ("water_target", 65, 7, 35, 4, b"\x41"),
        ("power_stage", 5, 3, 48, 2, b"\x01\x05"),
        ("power_stage", -1, 3, 48, 2, b"\x01\xff"),
        ("weather_enabled", False, 13, 50, 5, b"\x00"),
    ],
)
def test_commands_preserve_neighbour_settings(key, value, cmd, offset, length, expected):
    command, payload = setting_command(BoilerState.parse(CAPTURE), key, value)
    assert command == cmd
    assert payload[: len(expected)] == expected
    assert payload[len(expected) :] == CAPTURE[offset + len(expected) : offset + length]


def test_pump_mode_preserves_contour_timeout_and_reserved_bits():
    state = BoilerState.parse(CAPTURE)
    before = struct.unpack_from("<H", CAPTURE, 55)[0]
    cmd, payload = setting_command(state, "pump_mode", 2)
    after = struct.unpack("<H", payload)[0]
    assert cmd == 14
    assert after >> 3 & 3 == 2
    assert after & ~(3 << 3) == before & ~(3 << 3)


@pytest.mark.parametrize(
    "key,value",
    [
        ("air_target", 1),
        ("air_target", 36),
        ("air_target", math.nan),
        ("air_target", 20.01),
        ("water_target", 81),
        ("water_target", 49),
        ("water_target", 70.5),
        ("power_stage", 7),
        ("power_stage", -2),
        ("pump_mode", 0),
        ("enabled", 1),
        ("weather_enabled", "yes"),
        ("thermostat_type", 4),
        ("unknown", 0),
    ],
)
def test_invalid_controls_are_rejected(key, value):
    with pytest.raises(ZotaError):
        setting_command(BoilerState.parse(CAPTURE), key, value)


def test_standby_is_off_and_turn_on_command_is_explicit():
    raw = bytearray(CAPTURE)
    raw[84] |= 16
    assert not BoilerState.parse(bytes(raw)).enabled
    assert setting_command(BoilerState.parse(bytes(raw)), "enabled", True) == (20, b"\x01\x00")
    assert auth_frame(1234, 5678) == struct.pack("<HHHHHII", 0, 0, 12, 0, 24, 1234, 5678)


@pytest.mark.parametrize("raw", [CAPTURE[:-1], CAPTURE + b"\x00", b"\x02" + CAPTURE[1:]])
def test_unknown_data_layout_is_rejected(raw):
    with pytest.raises(ZotaError):
        BoilerState.parse(raw)
