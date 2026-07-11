"""
Custom integration to integrate generac with Home Assistant.

For more details about this integration, please refer to
https://github.com/technorat2/ha-generac
"""
import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GeneracApiClient
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
from .const import STARTUP_MESSAGE
from .coordinator import GeneracDataUpdateCoordinator

_LOGGER: logging.Logger = logging.getLogger(__package__)


def _enabled_platforms(entry: ConfigEntry) -> list[str]:
    """Return platforms enabled in the integration options."""
    return [platform for platform in PLATFORMS if entry.options.get(platform, True)]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME, "")
    password = entry.data.get(CONF_PASSWORD, "")
    access_token = entry.data.get(CONF_ACCESS_TOKEN, "")
    refresh_token = entry.data.get(CONF_REFRESH_TOKEN, "")
    expires_at = entry.data.get(CONF_EXPIRES_AT, 0)

    session = async_get_clientsession(hass)

    def update_tokens(tokens: dict[str, Any]) -> None:
        """Persist refreshed tokens without changing the user's credentials."""
        hass.config_entries.async_update_entry(entry, data={**entry.data, **tokens})

    client = GeneracApiClient(
        username,
        password,
        session,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        token_update_callback=update_tokens,
    )

    coordinator = GeneracDataUpdateCoordinator(hass, client=client)
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Unable to fetch Generac Mobile Link data")

    auth_mode = (
        AUTH_MODE_PKCE
        if client.auth_method.startswith("auth0")
        else AUTH_MODE_WEB_COOKIE
        if client.auth_method == "mobile_link_cookie"
        else None
    )
    if auth_mode and entry.data.get(CONF_AUTH_MODE) != auth_mode:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_AUTH_MODE: auth_mode}
        )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry, _enabled_platforms(entry)
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    domain_data = hass.data.get(DOMAIN, {})
    if entry.entry_id not in domain_data:
        return True

    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unloaded:
        domain_data.pop(entry.entry_id, None)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    if await async_unload_entry(hass, entry):
        await async_setup_entry(hass, entry)
