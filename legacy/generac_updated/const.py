"""Constants for Generac Updated Login."""
# Base component constants
NAME = "Generac Updated Login"
DOMAIN = "generac_updated"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.1.0"

ATTRIBUTION = (
    "Data provided by https://app.mobilelinkgen.com/api. "
    "This is reverse engineered. Heavily inspired by "
    "https://github.com/digitaldan/openhab-addons/blob/generac-2.0/bundles/org.openhab.binding.generacmobilelink/README.md"
)
ISSUE_URL = "https://github.com/bentekkie/ha-generac/issues"

# Platforms
BINARY_SENSOR = "binary_sensor"
SENSOR = "sensor"
WEATHER = "weather"
IMAGE = "image"
PLATFORMS = [BINARY_SENSOR, SENSOR, WEATHER, IMAGE]


# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_NAME = DOMAIN


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""


API_BASE = "https://app.mobilelinkgen.com/api"
AUTH0_SIGN_IN = f"{API_BASE}/Auth/Auth0/SignIn"
AUTH0_TOKEN_URL = "https://auth.ecobee.com/oauth/token"
AUTH0_CLIENT_ID = "USGUdyxRw1IrbXSY626wXXxZfnbS2R11"
AUTH0_AUDIENCE = "https://prod.ecobee.com/api/v1"
AUTH0_SCOPE = "openid profile offline_access"
AUTH0_PASSWORD_REALMS = ("Username-Password-Authentication",)
