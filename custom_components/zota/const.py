"""ZOTA integration constants."""

DOMAIN = "zota"
DEFAULT_INTERVAL = 300
DEFAULT_API_URL = "http://control.zota.ru:81"
CONF_API_URL = "api_url"
CONF_BOILER = "boiler"
CONF_INTERVAL = "update_interval"
CONF_ALLOW_HTTP = "allow_http"
CONF_ACCOUNT_TOKEN = "account_token"
MODEL = "MK_X"
BOILER_TYPE = 24
PUMP_MODES = {"auto": 1, "on": 2, "off": 3}
THERMOSTAT_TYPES = {"none": 0, "external": 1, "internal": 2, "opentherm": 3}
