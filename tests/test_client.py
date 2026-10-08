import asyncio
import struct
from contextlib import asynccontextmanager

import pytest
from conftest import CAPTURE
from zota_wire.api import Boiler, ZotaAccount, ZotaClient
from zota_wire.protocol import ZotaAuthError, ZotaError, frame


class Writer:
    def __init__(self):
        self.sent = []

    def write(self, data):
        self.sent.append(data)

    async def drain(self):
        pass


def reader_for(*packets):
    reader = asyncio.StreamReader()
    for packet in packets:
        reader.feed_data(packet)
    reader.feed_eof()
    return reader


def client():
    return ZotaClient(Boiler(1234, "Test", "unused.invalid", 5678))


async def test_fragmented_frame_and_matching_ack():
    reader = asyncio.StreamReader()
    data = (
        frame(1, 3, b"notification")
        + frame(1, 1, b"\x03\x00\x00\x00")
        + frame(1, 1, b"\x01\x00\x00\x00" + CAPTURE)
    )

    async def feed():
        for i in range(0, len(data), 3):
            reader.feed_data(data[i : i + 3])
            await asyncio.sleep(0)

    task = asyncio.create_task(feed())
    assert await client()._request(reader, Writer(), 1) == CAPTURE
    await task


@pytest.mark.parametrize("result,error", [(1, ZotaError), (3, ZotaAuthError), (100, ZotaError)])
async def test_rejected_command_is_never_success(result, error):
    with pytest.raises(error):
        await client()._request(reader_for(frame(1, 1, struct.pack("<HH", 9, result))), Writer(), 9)


async def test_oversized_header_rejected_before_reading_body():
    with pytest.raises(ZotaError):
        await client()._read_frame(reader_for(struct.pack("<HHH", 1, 1, 65535)))


async def test_control_reads_fresh_block_and_verifies_readback(monkeypatch):
    changed = bytearray(CAPTURE)
    struct.pack_into("<h", changed, 30, 215)
    reader = reader_for(
        frame(1, 1, b"\x01\x00\x00\x00" + CAPTURE),
        frame(1, 1, b"\x09\x00\x00\x00"),
        frame(1, 1, b"\x01\x00\x00\x00" + bytes(changed)),
    )
    writer = Writer()

    @asynccontextmanager
    async def connection():
        yield reader, writer

    api = client()
    monkeypatch.setattr(api, "_connection", connection)
    state = await api.set("air_target", 21.5)
    assert state.air_target == 21.5
    assert [struct.unpack_from("<H", p, 6)[0] for p in writer.sent] == [1, 9, 1]
    assert writer.sent[1][10:] == CAPTURE[32:35]


async def test_lost_ack_does_not_replay_write(monkeypatch):
    reader = reader_for(frame(1, 1, b"\x01\x00\x00\x00" + CAPTURE))
    writer = Writer()

    @asynccontextmanager
    async def connection():
        yield reader, writer

    api = client()
    monkeypatch.setattr(api, "_connection", connection)
    with pytest.raises(asyncio.IncompleteReadError):
        await api.set("air_target", 21.5)
    assert [struct.unpack_from("<H", p, 6)[0] for p in writer.sent].count(9) == 1


def test_http_requires_explicit_opt_in():
    with pytest.raises(ZotaError):
        ZotaAccount(None, "http://control.zota.ru:81", "user", "secret")
    ZotaAccount(None, "https://control.zota.ru", "user", "secret")


@pytest.mark.parametrize("internet_flag", [False, True, None])
async def test_account_lists_mk_x_regardless_of_internet_flag(monkeypatch, internet_flag):
    account = ZotaAccount(None, "https://control.zota.ru", "user", "secret")

    async def request(method, path, **kwargs):
        if path == "/token":
            return {"access_token": "test-token"}
        return {"boilers": [
            {"Type": "MK_X", "InternetConnection": internet_flag, "Serial": 1234,
             "Password": 5678, "Server": "unused.invalid", "BoilerName": "Test"},
            {"Type": "OTHER", "InternetConnection": True},
        ]}

    monkeypatch.setattr(account, "_request", request)
    assert await account.boilers() == [Boiler(1234, "Test", "unused.invalid", 5678)]


async def test_auth_failure_closes_tcp_connection(monkeypatch):
    class ClosingWriter(Writer):
        closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    writer = ClosingWriter()

    async def connect(*args):
        return reader_for(frame(0, 1, b"\x00\x00\x01\x00")), writer

    monkeypatch.setattr(asyncio, "open_connection", connect)
    with pytest.raises(ZotaAuthError):
        await client().fetch()
    assert writer.closed


async def test_full_tcp_control_transaction(monkeypatch):
    """Exercise auth, fresh read, grouped write and readback over loopback TCP."""
    wire_commands = []
    peer_done = asyncio.Event()
    peer_errors = []

    async def peer(reader, writer):
        raw = CAPTURE
        try:
            link, opcode, length = struct.unpack("<HHH", await reader.readexactly(6))
            auth = await reader.readexactly(length)
            assert (link, opcode) == (0, 0)
            assert struct.unpack("<HHII", auth) == (0, 24, 1234, 5678)
            writer.write(frame(0, 1, b"\x00\x00\x00\x00"))
            await writer.drain()
            for _ in range(3):
                link, opcode, length = struct.unpack("<HHH", await reader.readexactly(6))
                payload = await reader.readexactly(length)
                command = struct.unpack_from("<H", payload)[0]
                wire_commands.append(command)
                assert (link, opcode) == (1, 0)
                if command == 9:
                    assert payload[2:] == b"\xd7\x00" + CAPTURE[32:35]
                    raw = raw[:30] + payload[2:] + raw[35:]
                response = struct.pack("<HH", command, 0) + (raw if command == 1 else b"")
                writer.write(frame(1, 1, response))
                await writer.drain()
        except Exception as err:
            peer_errors.append(err)
        finally:
            writer.close()
            await writer.wait_closed()
            peer_done.set()

    server = await asyncio.start_server(peer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    real_connect = asyncio.open_connection

    async def local_connect(host, requested_port):
        assert host == "unused.invalid" and requested_port == 1977
        return await real_connect("127.0.0.1", port)

    monkeypatch.setattr(asyncio, "open_connection", local_connect)
    async with server:
        result = await client().set("air_target", 21.5)
        await asyncio.wait_for(peer_done.wait(), 2)
    assert not peer_errors
    assert wire_commands == [1, 9, 1]
    assert result.air_target == 21.5


async def test_ack_without_readback_confirmation_fails_without_rewrite(monkeypatch):
    api = client()
    calls = []

    @asynccontextmanager
    async def connection():
        yield None, None

    async def request(reader, writer, command, payload=b""):
        calls.append(command)
        return CAPTURE if command == 1 else b""

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr(api, "_connection", connection)
    monkeypatch.setattr(api, "_request", request)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    with pytest.raises(ZotaError, match="readback"):
        await api.set("air_target", 21.5)
    assert calls == [1, 9, 1, 1, 1]
