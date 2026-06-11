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

    def __init__(
        self,
        hass: HomeAssistant,
        api: BesteSchuleApi,
        student: dict[str, Any] | None = None,
        students: Any | None = None,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.api = api
        self.student = student
        self.students = students
        self.student_id = (
            str(student["id"])
            if isinstance(student, dict) and student.get("id") is not None
            else "student"
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from beste.schule."""
        try:
            return await self.api.fetch_overview(self.student, self.students)
        except BesteSchuleApiError as err:
            raise UpdateFailed(str(err)) from err

    def unique_id_prefix(self, entry_id: str) -> str:
        """Return the entity unique id prefix for this child."""
        if isinstance(self.data, dict) and self.data.get("multi_student"):
            return f"{entry_id}_{self.student_id}"
        return entry_id


def coordinators_for_entry(
    hass: HomeAssistant,
    entry_id: str,
) -> list[BesteSchuleDataUpdateCoordinator]:
    """Return all child coordinators for a config entry."""
    value = hass.data[DOMAIN][entry_id]
    if isinstance(value, list):
        return value
    return [value]
