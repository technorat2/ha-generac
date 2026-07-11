"""Constants for Generac Updated Login."""
# Base component constants
NAME = "Generac Updated Login"
DOMAIN = "generac_auth0_pkce"
VERSION = "0.3.1"

ATTRIBUTION = (
    "Data provided by https://app.mobilelinkgen.com/api. "
    "This is reverse engineered. Heavily inspired by "
    "https://github.com/digitaldan/openhab-addons/blob/generac-2.0/bundles/org.openhab.binding.generacmobilelink/README.md"
)
ISSUE_URL = "https://github.com/technorat2/ha-generac/issues"

# Platforms
BINARY_SENSOR = "binary_sensor"
SENSOR = "sensor"
WEATHER = "weather"
IMAGE = "image"
PLATFORMS = [BINARY_SENSOR, SENSOR, WEATHER, IMAGE]


# Configuration
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
API_V5_BASE = f"{API_BASE}/v5"
MOBILE_API_USER_AGENT = "okhttp/4.12.0"
AUTH0_SIGN_IN = f"{API_BASE}/Auth/Auth0/SignIn"
AUTH0_AUTHORIZE_URL = "https://auth.ecobee.com/authorize"
AUTH0_TOKEN_URL = "https://auth.ecobee.com/oauth/token"
AUTH0_CLIENT_ID = "USGUdyxRw1IrbXSY626wXXxZfnbS2R11"
AUTH0_AUDIENCE = "https://prod.ecobee.com/api/v1"
AUTH0_SCOPE = "openid email offline_access invoke:api"
AUTH0_CLIENT_HEADER = (
    "eyJuYW1lIjoicmVhY3QtbmF0aXZlLWF1dGgwIiwidmVyc2lvbiI6IjUuNC4wIn0="
)
AUTH0_REDIRECT_URI = (
    "com.generac.standbystatus://auth.ecobee.com/android/"
    "com.generac.standbystatus/callback"
)
CONF_AUTH_MODE = "auth_mode"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
AUTH_MODE_PKCE = "pkce"
AUTH_MODE_WEB_COOKIE = "web_cookie"
