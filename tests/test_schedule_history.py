"""Schedule integrity, conflict guard, single writes and archive normalization."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from conftest import CAPTURE
from test_extended import PROGRAM
from zota_wire.api import Boiler, ZotaAccount, ZotaClient
from zota_wire.history import get_history, utc_time
from zota_wire.protocol import BoilerState, ZotaError
from zota_wire.schedule import patch_program, revision


def test_schedule_patch_preserves_flags_and_other_periods():
    raw = patch_program(PROGRAM, BoilerState.parse(CAPTURE), [{"period_index": 0, "air_target": 22.1}])
    assert raw[:7] == PROGRAM[:7] and raw[9:] == PROGRAM[9:]
    assert raw[5] == 16  # Unknown high flags are preserved, not reconstructed.
    assert raw[7:9] == b"\xdd\x00"


def test_schedule_known_flag_patch_preserves_unknown_flags():
    raw = patch_program(PROGRAM, BoilerState.parse(CAPTURE), [{"period_index": 0, "use_air": True}])
    assert raw[5] == 18
    assert raw[:5] == PROGRAM[:5] and raw[6:] == PROGRAM[6:]


@pytest.mark.parametrize("changes", [
    [], [{"period_index": 8, "air_target": 22}], [{"period_index": 0, "air_target": 35.1}],
    [{"period_index": 0, "air_target": 22.01}], [{"period_index": 0, "end": 7}],
    [{"period_index": 0, "unknown": 1}], [{"period_index": 0, "use_air": 1}],
    [{"period_index": 0, "power_stage": 7}], [{"period_index": 0, "program_index": 1, "end": 6}],
    [{"period_index": 0, "air_target": 22}, {"period_index": 0, "air_target": 23}],
])
def test_invalid_schedule_changes_rejected(changes):
    with pytest.raises(ZotaError):
        patch_program(PROGRAM, BoilerState.parse(CAPTURE), changes)


def test_adjacent_period_boundaries_can_change_together():
    updated = patch_program(PROGRAM, BoilerState.parse(CAPTURE), [
        {"period_index": 0, "end": 7}, {"period_index": 1, "begin": 7}])
    assert updated[4] == 7 and updated[11] == 7


def mocked_client(monkeypatch, readback=None, lose_ack=False):
    client = ZotaClient(Boiler(1234, "Test", "unused.invalid", 0))
    calls, saved = [], [PROGRAM]

    @asynccontextmanager
    async def connection():
        yield None, None

    async def request(reader, writer, command, payload=b""):
        calls.append(command)
        if command == 1:
            return CAPTURE
        if command == 2:
            return readback if readback is not None and 18 in calls else saved[0]
        assert command == 18
        if lose_ack:
            raise ZotaError("Connection lost")
        saved[0] = payload
        return b""

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr(client, "_connection", connection)
    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    return client, calls


async def test_schedule_preview_never_writes(monkeypatch):
    client, calls = mocked_client(monkeypatch)
    result = await client.schedule([{"period_index": 0, "air_target": 22.1}])
    assert calls == [2, 1]
    assert result["before"]["revision"] == revision(PROGRAM)
    assert result["changed"]


async def test_schedule_conflict_prevents_write(monkeypatch):
    client, calls = mocked_client(monkeypatch)
    with pytest.raises(ZotaError, match="changed since preview"):
        await client.schedule([{"period_index": 0, "air_target": 22.1}], "0" * 64, True)
    assert 18 not in calls


async def test_schedule_write_is_verified(monkeypatch):
    client, calls = mocked_client(monkeypatch)
    result = await client.schedule([{"period_index": 0, "air_target": 22.1}], revision(PROGRAM), True)
    assert result["confirmed"] and calls == [2, 1, 18, 2]


async def test_live_guard_rejects_active_thermostat_before_write(monkeypatch):
    client, calls = mocked_client(monkeypatch)
    original_request = client._request

    async def request(reader, writer, command, payload=b""):
        data = await original_request(reader, writer, command, payload)
        if command == 1:
            data = data[:11] + b"\x02" + data[12:]
        return data

    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(ZotaError, match="cancelled"):
        await client.schedule([{"period_index": 0, "air_target": 22.1}], revision(PROGRAM), True,
                              require_inactive=True)
    assert 18 not in calls


@pytest.mark.parametrize("lose_ack", [True, False])
async def test_schedule_failure_never_replays_write(monkeypatch, lose_ack):
    client, calls = mocked_client(monkeypatch, readback=PROGRAM, lose_ack=lose_ack)
    with pytest.raises(ZotaError):
        await client.schedule([{"period_index": 0, "air_target": 22.1}], revision(PROGRAM), True)
    assert calls.count(18) == 1


async def test_history_utc_step_units_and_unknown_sensors(monkeypatch):
    async def request(self, method, path, **kwargs):
        assert method == "GET" and path.endswith("GetBoilerHistory")
        assert kwargs["params"]["startDate"] == "2026-10-08T09:00"
        assert kwargs["params"]["offset"] == "1"
        return {"response": {"Result": 0}, "boilersData": [{
            "Time": "2026-10-08T09:10:00Z", "Info": {"TempRoom": 179, "TempWater": 50,
            "TempDHW": 16385, "Pressure": 916, "CurPower": 3}, "Data": "excluded",
        }]}

    monkeypatch.setattr(ZotaAccount, "_request", request)
    result = await get_history(None, "https://control.zota.ru", "test-token", False, 1234,
                               "2026-10-08T12:00:00+03:00", "2026-10-08T13:00:00+03:00",
                               (0, 1.5, 3, 4.5))
    sample = result["samples"][0]
    assert sample["air_temp"] == 17.9 and sample["pressure"] == .916
    assert sample["dhw_temp"] is None and sample["power_kw"] == 4.5
    assert "Data" not in sample


@pytest.mark.parametrize("value", ["bad", "2026-10-08T12:00:00", "", None])
def test_archive_dates_require_explicit_timezone(value):
    with pytest.raises(ZotaError):
        utc_time(value)


async def test_archive_range_rejected_before_network_request():
    with pytest.raises(ZotaError, match="31 days"):
        await get_history(None, "https://control.zota.ru", "", False, 1,
                          "2026-09-01T00:00:00Z", "2026-10-08T00:00:00Z", (0,))
