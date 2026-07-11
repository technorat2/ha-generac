import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import CannotConnectException
from .api import GeneracApiClient
from .api import SessionExpiredException
from .const import DOMAIN
from .models import Item

SCAN_INTERVAL = timedelta(seconds=30)

_LOGGER: logging.Logger = logging.getLogger(__package__)


class GeneracDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Item]]):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, client: GeneracApiClient) -> None:
        """Initialize."""
        self.api = client
        self.is_online = False

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[str, Item]:
        """Update data via library."""
        try:
            _LOGGER.debug("Refreshing Generac Mobile Link data")
            items = await self.api.async_get_data()
            if items is None:
                raise CannotConnectException("Generac Mobile Link returned no data")
            self.is_online = True
            return items
        except CannotConnectException as exception:
            self.is_online = False
            raise UpdateFailed(
                "Unable to connect to Generac Mobile Link"
            ) from exception
        except SessionExpiredException as exception:
            self.is_online = False
            raise UpdateFailed("Generac Mobile Link session expired") from exception
        except Exception as exception:
            self.is_online = False
            _LOGGER.exception("Unexpected error refreshing Generac Mobile Link data")
            raise UpdateFailed(
                "Unexpected error refreshing Generac data"
            ) from exception
