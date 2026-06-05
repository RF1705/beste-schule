"""Data coordinator for beste.schule."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BesteSchuleApi, BesteSchuleApiError
from .const import DOMAIN

LOGGER = logging.getLogger(__name__)


class BesteSchuleDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate beste.schule data updates."""

    def __init__(self, hass: HomeAssistant, api: BesteSchuleApi) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from beste.schule."""
        try:
            return await self.api.fetch_overview()
        except BesteSchuleApiError as err:
            raise UpdateFailed(str(err)) from err
