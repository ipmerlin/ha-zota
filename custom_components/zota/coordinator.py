"""Central poll and control handling."""

import logging
from dataclasses import replace
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZotaClient
from .const import CONF_INTERVAL, DEFAULT_INTERVAL
from .protocol import BoilerState, ZotaAuthError, ZotaError

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

    async def _async_update_data(self):
        try:
            return await self.client.fetch(extended=True)
        except ZotaAuthError as err:
            raise ConfigEntryAuthFailed("ZOTA boiler authentication failed") from err
        except ZotaError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set(self, key, value):
        try:
            state = await self.client.set(key, value)
        except ZotaError as err:
            # Drop stale optimistic UI state after any failed/uncertain command.
            self.async_set_update_error(UpdateFailed(str(err)))
            await self.async_request_refresh()
            raise HomeAssistantError(str(err)) from err
        self.async_set_updated_data(replace(state, details=self.data.details if self.data else None))
