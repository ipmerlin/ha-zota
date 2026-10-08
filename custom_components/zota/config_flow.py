"""Account login, boiler selection and polling options."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZotaAccount, ZotaClient
from .const import (
    CONF_ACCOUNT_TOKEN,
    CONF_ALLOW_HTTP,
    CONF_API_URL,
    CONF_BOILER,
    CONF_INTERVAL,
    DEFAULT_API_URL,
    DEFAULT_INTERVAL,
    DOMAIN,
)
from .protocol import ZotaAuthError, ZotaError


class ZotaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._boilers = {}
        self._settings = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                account = ZotaAccount(
                    async_get_clientsession(self.hass),
                    user_input[CONF_API_URL],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_ALLOW_HTTP],
                )
                boilers = await account.boilers()
                self._boilers = {str(b.serial): b for b in boilers}
                self._settings = {k: user_input[k] for k in (CONF_USERNAME, CONF_API_URL, CONF_ALLOW_HTTP)}
                self._settings[CONF_ACCOUNT_TOKEN] = account.token
                if not boilers:
                    errors["base"] = "no_boilers"
                elif self.source in (config_entries.SOURCE_REAUTH, config_entries.SOURCE_RECONFIGURE):
                    entry = (self._get_reauth_entry() if self.source == config_entries.SOURCE_REAUTH
                             else self._get_reconfigure_entry())
                    serial = str(entry.data[CONF_BOILER]["serial"])
                    if serial not in self._boilers:
                        errors["base"] = "boiler_missing"
                    else:
                        await ZotaClient(self._boilers[serial]).fetch()
                        return self.async_update_reload_and_abort(
                            entry,
                            data_updates={**self._settings, CONF_BOILER: self._boilers[serial].as_config()},
                        )
                else:
                    return await self.async_step_boiler()
            except ZotaAuthError:
                errors["base"] = "invalid_auth"
            except ZotaError:
                errors["base"] = "cannot_connect"
        defaults = user_input or self._settings
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_API_URL, default=defaults.get(CONF_API_URL, DEFAULT_API_URL)): str,
                    vol.Required(CONF_ALLOW_HTTP, default=defaults.get(CONF_ALLOW_HTTP, False)): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_boiler(self, user_input=None):
        errors = {}
        if user_input is not None:
            boiler = self._boilers[user_input[CONF_BOILER]]
            await self.async_set_unique_id(f"mk_x_{boiler.serial}")
            self._abort_if_unique_id_configured()
            try:
                await ZotaClient(boiler).fetch()
            except ZotaAuthError:
                errors["base"] = "invalid_auth"
            except ZotaError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=boiler.name, data={**self._settings, CONF_BOILER: boiler.as_config()}
                )
        return self.async_show_form(
            step_id="boiler",
            data_schema=vol.Schema(
                {vol.Required(CONF_BOILER): vol.In({k: f"{b.name} ({k})" for k, b in self._boilers.items()})}
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        self._settings = entry_data
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input=None):
        self._settings = self._get_reconfigure_entry().data
        return await self.async_step_user(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZotaOptionsFlow()


class ZotaOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERVAL, default=self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
                    ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600))
                }
            ),
        )
