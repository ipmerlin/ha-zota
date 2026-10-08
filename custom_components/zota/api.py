"""Async ZOTA account API and serialized MK-X TCP transactions."""

from __future__ import annotations

import asyncio
import struct
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from urllib.parse import urlparse

import aiohttp

from .const import MODEL
from .protocol import (
    BoilerState,
    ZotaAuthError,
    ZotaError,
    auth_frame,
    command_frame,
    parse_info,
    parse_program,
    setting_command,
    setting_matches,
)


@dataclass(frozen=True)
class Boiler:
    serial: int
    name: str
    server: str
    password: int = field(repr=False)

    def as_config(self) -> dict:
        return {
            "serial": self.serial,
            "name": self.name,
            "server": self.server,
            "password": self.password,
            "model": MODEL,
        }


class ZotaAccount:
    """Use the application's account endpoints. No implicit TLS downgrade."""

    def __init__(
        self, session: aiohttp.ClientSession, url: str, username: str, password: str, allow_http: bool = False
    ) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ZotaError("Invalid API URL")
        if parsed.scheme == "http" and not allow_http:
            raise ZotaError("HTTP requires explicit opt-in")
        self.session = session
        self.url = url.rstrip("/")
        self.username = username
        self._password = password
        self._token: str | None = None

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            async with self.session.request(
                method,
                self.url + path,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=False,
                **kwargs,
            ) as response:
                if response.status in (400, 401, 403) and path == "/token":
                    raise ZotaAuthError("Account credentials rejected")
                if response.status in (401, 403):
                    raise ZotaAuthError("Account session rejected")
                if response.status != 200:
                    raise ZotaError(f"ZOTA API HTTP {response.status}")
                data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    raise ZotaError("Invalid ZOTA API response")
                return data
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            # Do not include server bodies, headers or URLs in error messages.
            raise ZotaError("Cannot communicate with ZOTA account API") from err

    async def boilers(self) -> list[Boiler]:
        auth = await self._request(
            "POST",
            "/token",
            data={"username": self.username, "password": self._password, "grant_type": "password"},
        )
        token = auth.get("access_token")
        if not isinstance(token, str) or not token:
            raise ZotaAuthError("Missing account token")
        self._token = token
        data = await self._request(
            "GET", "/api/Boilers/GetBoilers", headers={"Authorization": f"Bearer {token}"}
        )
        rows = data.get("boilers")
        if not isinstance(rows, list):
            raise ZotaError("Missing boiler list")
        result = []
        try:
            for row in rows:
                # The account flag can be false even for a reachable cloud boiler.
                # Verify connectivity with a telemetry read during configuration.
                if row.get("Type") != MODEL:
                    continue
                serial, password = int(row["Serial"]), int(row["Password"])
                server = str(row["Server"])
                if not 0 <= serial <= 0xFFFFFFFF or not 0 <= password <= 0xFFFFFFFF or not server:
                    raise ValueError
                result.append(
                    Boiler(serial, row.get("BoilerName") or f"ZOTA MK-X {serial}", server, password)
                )
        except (KeyError, TypeError, ValueError) as err:
            raise ZotaError("Invalid boiler connection details") from err
        return result

    @property
    def token(self) -> str | None:
        """Account access token for optional history requests, never the password."""
        return self._token


class ZotaClient:
    """One connection per transaction; no command replay or persistent reader."""

    def __init__(self, boiler: Boiler, timeout: float = 25) -> None:
        self.boiler = boiler
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._info = {}

    @asynccontextmanager
    async def _connection(self):
        writer = None
        try:
            async with asyncio.timeout(self.timeout):
                reader, writer = await asyncio.open_connection(self.boiler.server, 1977)
                writer.write(auth_frame(self.boiler.serial, self.boiler.password))
                await writer.drain()
                for _ in range(20):
                    link, opcode, payload = await self._read_frame(reader)
                    if (link, opcode) == (0, 1):
                        if len(payload) != 4 or struct.unpack("<HH", payload) != (0, 0):
                            raise ZotaAuthError("Boiler credentials rejected")
                        break
                else:
                    raise ZotaError("Missing boiler authorization response")
                yield reader, writer
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            raise ZotaError("Connection failed or timed out; command outcome may be unknown") from err
        finally:
            if writer is not None:
                writer.close()
                try:
                    async with asyncio.timeout(2):
                        await writer.wait_closed()
                except (OSError, TimeoutError):
                    pass

    async def _read_frame(self, reader) -> tuple[int, int, bytes]:
        link, opcode, length = struct.unpack("<HHH", await reader.readexactly(6))
        if link > 2 or opcode > 4 or length > 4096:
            raise ZotaError("Invalid ZOTA frame header")
        return link, opcode, await reader.readexactly(length)

    async def _request(self, reader, writer, command: int, payload: bytes = b"") -> bytes:
        writer.write(command_frame(command, payload))
        await writer.drain()
        for _ in range(40):
            link, opcode, body = await self._read_frame(reader)
            if (link, opcode) != (1, 1):
                continue  # Notifications and NOP are not command acknowledgements.
            if len(body) < 4:
                raise ZotaError("Truncated command response")
            code, result = struct.unpack_from("<HH", body)
            if code != command:
                continue
            if result == 3:
                raise ZotaAuthError("Boiler denied access")
            if result:
                raise ZotaError(f"Boiler rejected command {command}: result {result}")
            return body[4:]
        raise ZotaError("Missing matching command response")

    async def fetch(self, extended: bool = False) -> BoilerState:
        async with self._lock, self._connection() as (reader, writer):
            state = BoilerState.parse(await self._request(reader, writer, 1))
            if not extended:
                return state
            details = dict(self._info)
            try:
                if not self._info:
                    self._info = parse_info(await self._request(reader, writer, 0))
                    details.update(self._info)
                details.update(parse_program(await self._request(reader, writer, 2)))
            except ZotaAuthError:
                raise
            except ZotaError:
                # Optional unsupported data must not hide valid main telemetry.
                pass
            return replace(state, details=details)

    async def set(self, key: str, value) -> BoilerState:
        async with self._lock, self._connection() as (reader, writer):
            before = BoilerState.parse(await self._request(reader, writer, 1))
            command, payload = setting_command(before, key, value)
            if setting_matches(before, key, value):
                return before
            await self._request(reader, writer, command, payload)
            # Read-only retries allow time for the controller to publish its state.
            for attempt in range(3):
                after = BoilerState.parse(await self._request(reader, writer, 1))
                if setting_matches(after, key, value):
                    return after
                if attempt < 2:
                    await asyncio.sleep(1)
            raise ZotaError("Command acknowledged, but readback does not confirm the requested value")

    async def schedule(self, changes=None, expected_revision=None, write=False, require_inactive=False) -> dict:
        from .schedule import patch_program, program_view, revision

        async with self._lock, self._connection() as (reader, writer):
            raw = await self._request(reader, writer, 2)
            before = program_view(raw)
            if changes is None:
                return before
            state = BoilerState.parse(await self._request(reader, writer, 1))
            if write and require_inactive and (state.raw[11] != 0 or state.raw[60] & 1):
                raise ZotaError("Live schedule test cancelled: native thermostat is enabled or active")
            patched = patch_program(raw, state, changes)
            preview = {"before": before, "after": program_view(patched), "changed": raw != patched}
            if not write:
                return preview
            if expected_revision != revision(raw):
                raise ZotaError("Schedule changed since preview; obtain a new preview before saving")
            if patched == raw:
                return {**preview, "confirmed": True}
            await self._request(reader, writer, 18, patched)
            for attempt in range(3):
                after = await self._request(reader, writer, 2)
                if after == patched:
                    return {**preview, "after": program_view(after), "confirmed": True}
                if attempt < 2:
                    await asyncio.sleep(1)
            raise ZotaError("Schedule acknowledged but readback differs; no automatic write retry")
