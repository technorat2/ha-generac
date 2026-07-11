"""Adds config flow for generac."""
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import Auth0PkceSession
from .api import AuthFlowUnavailableException
from .api import CannotConnectException
from .api import GeneracApiClient
from .api import InvalidCredentialsException
from .api import SessionExpiredException
from .const import AUTH_MODE_PKCE
from .const import AUTH_MODE_WEB_COOKIE
from .const import CONF_ACCESS_TOKEN
from .const import CONF_AUTH_MODE
from .const import CONF_EXPIRES_AT
from .const import CONF_PASSWORD
from .const import CONF_REFRESH_TOKEN
from .const import CONF_USERNAME
from .const import DOMAIN
from .const import PLATFORMS


_LOGGER: logging.Logger = logging.getLogger(__package__)


class GeneracFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for generac."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            result = await self._exchange_and_test(
                username, user_input[CONF_PASSWORD]
            )
            error = result.get("error")
            if error is None:
                await self.async_set_unique_id(username.casefold())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=username, data=result
                )
            else:
                self._errors["base"] = error

            return await self._show_config_form(user_input)

        return await self._show_config_form(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GeneracOptionsFlowHandler(config_entry)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the Mobile Link credential form."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=self._errors,
        )

    async def _exchange_and_test(
        self, username: str, password: str
    ) -> dict[str, Any]:
        """Run Auth0 PKCE hosted login, test tokens, and return config data."""
        session = async_create_clientsession(self.hass)
        try:
            token_data = await Auth0PkceSession.login_with_hosted_forms(
                session, username, password
            )
            client = GeneracApiClient(
                username,
                password,
                session,
                access_token=str(token_data.get(CONF_ACCESS_TOKEN, "")),
                refresh_token=str(token_data.get(CONF_REFRESH_TOKEN, "")),
                expires_at=float(token_data.get(CONF_EXPIRES_AT, 0)),
            )
            data = await client.async_get_data()
            if data is None:
                raise CannotConnectException("Generac Mobile Link returned no data")
            if not client.auth_method.startswith("auth0"):
                raise SessionExpiredException("Auth0 login did not produce bearer access")
            return {
                CONF_AUTH_MODE: AUTH_MODE_PKCE,
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_ACCESS_TOKEN: client.access_token,
                CONF_REFRESH_TOKEN: client.refresh_token,
                CONF_EXPIRES_AT: client.expires_at,
            }
        except InvalidCredentialsException as exception:
            _LOGGER.debug("Generac/Auth0 rejected login: %s", exception)
            return {"error": "auth"}
        except (
            AuthFlowUnavailableException,
            CannotConnectException,
            SessionExpiredException,
            aiohttp.ClientError,
        ) as pkce_error:
            _LOGGER.debug(
                "Generac Updated Login PKCE setup failed; trying cookie bridge fallback: %s",
                pkce_error,
            )
        except Exception:
            _LOGGER.exception("Unexpected error while testing Generac Updated Login")
            return {"error": "internal"}

        try:
            async with aiohttp.ClientSession() as fallback_session:
                client = GeneracApiClient(username, password, fallback_session)
                data = await client.async_get_data()
            if data is None:
                raise CannotConnectException("Generac Mobile Link returned no data")
            return {
                CONF_AUTH_MODE: AUTH_MODE_WEB_COOKIE,
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
            }
        except InvalidCredentialsException as e:
            _LOGGER.debug("Generac/Auth0 rejected login: %s", e)
            return {"error": "auth"}
        except CannotConnectException as e:
            _LOGGER.debug("Unable to connect to Generac Mobile Link: %s", e)
            return {"error": "cannot_connect"}
        except SessionExpiredException as e:
            _LOGGER.debug("Generac Mobile Link rejected API session: %s", e)
            return {"error": "cannot_connect"}
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error while testing Generac Updated Login: %s", e)
            return {"error": "internal"}


class GeneracOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options handler for generac."""

    def __init__(self, config_entry):
        """Initialize HACS options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(x, default=self.options.get(x, True)): bool
                    for x in sorted(PLATFORMS)
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(
            title=self.config_entry.data.get(CONF_USERNAME), data=self.options
        )
