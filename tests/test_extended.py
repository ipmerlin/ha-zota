"""Validate expanded commands against captured byte layout and TCP readback."""

import struct
from contextlib import asynccontextmanager

import pytest
from conftest import CAPTURE
from zota_wire.api import Boiler, ZotaClient
from zota_wire.protocol import (
    BoilerState,
    ZotaError,
    fault_details,
    frame,
    parse_info,
    parse_program,
    setting_command,
    setting_matches,
)
from zota_wire.settings import SELECTS, SETTINGS, SWITCHES, read_setting, setting_limits

PROGRAM = bytes.fromhex(
    "03010500061037dc004b030609003704014b0309100037b4004b031017003704014b0317183037dc004b03"
)


def valid_value(key):
    if key in SWITCHES:
        return not read_setting(CAPTURE, key)
    if key in SELECTS:
        return next(iter(SELECTS[key][1].values()))
    low, _ = setting_limits(CAPTURE, key)
    # Keep the water setpoint within updated bounds.
    return 80 if key == "water_max" else low


@pytest.mark.parametrize("key", list(SETTINGS))
def test_expanded_command_changes_only_selected_field(key):
    spec = SETTINGS[key]
    value = valid_value(key)
    command, payload = setting_command(BoilerState.parse(CAPTURE), key, value)
    assert command == spec.command and len(payload) == spec.end - spec.start
    updated = CAPTURE[:spec.start] + payload + CAPTURE[spec.end:]
    assert setting_matches(BoilerState.parse(updated), key, value)
    changed_bits = int.from_bytes(CAPTURE[spec.start:spec.end], "little") ^ int.from_bytes(payload, "little")
    if spec.width:
        mask = ((1 << spec.width) - 1) << (8 * (spec.offset - spec.start) + spec.shift)
    else:
        mask = 255 << (8 * (spec.offset - spec.start))
    assert changed_bits & ~mask == 0


@pytest.mark.parametrize("key,value", [
    ("pressure_min", 2), ("pressure_max", 1), ("dhw_target", 80),
    ("air_hysteresis_upper", 0.01), ("air_correction", -11),
    ("valve_type", 2), ("external_contact", 3), ("power_on_delay", 1),
    ("external_power_stage", 7), ("water_max", 65),
])
def test_expanded_invalid_settings_rejected(key, value):
    with pytest.raises(ZotaError):
        setting_command(BoilerState.parse(CAPTURE), key, value)


def test_captured_information_and_program():
    assert parse_info(bytes.fromhex("5a001c10")) == {
        "nominal_power": 9, "firmware": "1.12", "indicator_firmware": "1.0",
    }
    program = parse_program(PROGRAM)
    assert program["program_mode"] == 1
    assert len(program["program_periods"]) == 5
    assert program["program_periods"][0] == {
        "program_index": 0, "begin": 0, "end": 6, "flags": 16, "dhw_target": 55,
        "air_target": 22, "water_target": 75, "power_stage": 3,
    }


@pytest.mark.parametrize("raw", [b"", PROGRAM[:-1], PROGRAM + b"\x00", b"\x03\x01\x09", b"\x04\x01\x00"])
def test_malformed_program_rejected(raw):
    with pytest.raises(ZotaError):
        parse_program(raw)


def test_fault_decode_keeps_sensor_codes_separate():
    assert fault_details((1 << 5) | (2 << 10)) == {
        "active_faults": ["high_pressure"], "sensor_error_codes": {"water": 2},
    }
    assert fault_details((1 << 3) | (1 << 12), True) == {
        "active_faults": ["low_water_temperature"], "sensor_error_codes": {"aux": 1},
    }


@pytest.mark.parametrize("key", list(SETTINGS))
async def test_expanded_write_ack_and_telemetry_readback(monkeypatch, key):
    """Use real frame parsing, preserving the controller's unrelated block bytes."""
    import asyncio

    value = valid_value(key)
    command, payload = setting_command(BoilerState.parse(CAPTURE), key, value)
    spec = SETTINGS[key]
    raw = CAPTURE[:spec.start] + payload + CAPTURE[spec.end:]
    reader = asyncio.StreamReader()
    for code, body in ((1, CAPTURE), (command, b""), (1, raw)):
        reader.feed_data(frame(1, 1, struct.pack("<HH", code, 0) + body))
    reader.feed_eof()
    sent = []

    class Writer:
        def write(self, data):
            sent.append(data)

        async def drain(self):
            pass

    @asynccontextmanager
    async def connection():
        yield reader, Writer()

    client = ZotaClient(Boiler(1234, "Test", "unused.invalid", 0))
    monkeypatch.setattr(client, "_connection", connection)
    result = await client.set(key, value)
    assert setting_matches(result, key, value)
    expected = [1] if read_setting(CAPTURE, key) == value else [1, command, 1]
    assert [struct.unpack_from("<H", packet, 6)[0] for packet in sent] == expected


async def test_extended_poll_reads_info_and_program_without_writes(monkeypatch):
    import asyncio

    reader = asyncio.StreamReader()
    for command, data in ((1, CAPTURE), (0, bytes.fromhex("5a001c10")), (2, PROGRAM)):
        reader.feed_data(frame(1, 1, struct.pack("<HH", command, 0) + data))
    reader.feed_eof()
    commands = []

    class Writer:
        def write(self, data):
            commands.append(struct.unpack_from("<H", data, 6)[0])

        async def drain(self):
            pass

    @asynccontextmanager
    async def connection():
        yield reader, Writer()

    client = ZotaClient(Boiler(1234, "Test", "unused.invalid", 0))
    monkeypatch.setattr(client, "_connection", connection)
    state = await client.fetch(extended=True)
    assert commands == [1, 0, 2]
    assert state.values()["firmware"] == "1.12"
    assert len(state.values()["program_periods"]) == 5
    assert state.values()["air_temp"] == 17.4


async def test_unsupported_optional_info_keeps_main_telemetry(monkeypatch):
    client = ZotaClient(Boiler(1234, "Test", "unused.invalid", 0))

    @asynccontextmanager
    async def connection():
        yield None, None

    async def request(reader, writer, command):
        if command == 1:
            return CAPTURE
        raise ZotaError("Unsupported optional data")

    monkeypatch.setattr(client, "_connection", connection)
    monkeypatch.setattr(client, "_request", request)
    state = await client.fetch(extended=True)
    assert state.raw == CAPTURE and state.values()["air_temp"] == 17.4
