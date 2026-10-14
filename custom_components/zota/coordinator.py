"""Central poll and control handling."""

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZotaClient
from .const import CONF_INTERVAL, DEFAULT_INTERVAL
from .protocol import BoilerState, ZotaAuthError, ZotaConnectionError, ZotaError

_LOGGER = logging.getLogger(__name__)


class ZotaCoordinator(DataUpdateCoordinator[BoilerState]):
    def __init__(self, hass, entry, client: ZotaClient):
        super().__init__(
            hass,
            _LOGGER,
            name="ZOTA MK-X",
            config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
            always_update=False,
        )
        self.client = client
        self._post_command_refresh_cancels = []
        self._post_command_refresh_generation = 0

    def async_cancel_post_command_refresh(self):
        """Cancel follow-up reads on a new command or integration unload."""
        for cancel in self._post_command_refresh_cancels:
            cancel()
        self._post_command_refresh_cancels.clear()
        self._post_command_refresh_generation += 1

    async def async_refresh_after_command(self):
        """Read all telemetry now, then catch delayed cloud/controller changes."""
        self.async_cancel_post_command_refresh()
        generation = self._post_command_refresh_generation
        await self.async_refresh()
        if generation != self._post_command_refresh_generation:
            return

        async def refresh(_now):
            if generation == self._post_command_refresh_generation:
                await self.async_refresh()

        for delay in (10, 30):
            self._post_command_refresh_cancels.append(async_call_later(self.hass, delay, refresh))

    async def _async_update_data(self):
        try:
            try:
                state = await self.client.fetch(extended=True)
            except ZotaConnectionError:
                # Retry only a read, through a fresh authenticated connection.
                await asyncio.sleep(2)
                state = await self.client.fetch(extended=True)
            if self.data and self.data.details:
                state = replace(state, details={**self.data.details, **(state.details or {})})
            return state
        except ZotaAuthError as err:
            raise ConfigEntryAuthFailed("ZOTA boiler authentication failed") from err
        except ZotaError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set(self, key, value):
        try:
            state = await self.client.set(key, value)
        except ZotaError as err:
            # A failed write does not prove sensors are offline. A fresh read
            # determines availability and resolves any uncertain command outcome.
            await self.async_refresh()
            raise HomeAssistantError(str(err)) from err
        self.async_set_updated_data(replace(state, details=self.data.details if self.data else None))
        await self.async_refresh_after_command()
