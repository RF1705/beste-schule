"""Data coordinator for beste.schule."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BesteSchuleApi, BesteSchuleApiError, BesteSchuleAuthError
from .const import DOMAIN
from .entity import student_id_from_data

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
        self._student_id_resolved = False
        self.data_revision = 0
        self.timetable_generated_cache: dict[
            bool, tuple[tuple[int, Any], list[Any]]
        ] = {}
        self.timetable_card_cache: dict[tuple[int, Any, int], list[dict[str, Any]]] = {}
        self.timetable_history_generation = 0
        self.timetable_history_saved_generation = 0
        self.lesson_boundary_manager: Any | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from beste.schule."""
        try:
            data = await self.api.fetch_overview(self.student, self.students)
        except BesteSchuleAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BesteSchuleApiError as err:
            raise UpdateFailed(str(err)) from err
        if not self._student_id_resolved:
            self.student_id = student_id_from_data(data)
            self._student_id_resolved = True
        data["identifier_student_id"] = self.student_id
        self.data_revision += 1
        self.timetable_generated_cache.clear()
        self.timetable_card_cache.clear()
        return data

    def unique_id_prefix(self, entry_id: str) -> str:
        """Return the entity unique id prefix for this child."""
        return f"{entry_id}_{self.student_id}"


def coordinators_for_entry(
    hass: HomeAssistant,
    entry_id: str,
) -> list[BesteSchuleDataUpdateCoordinator]:
    """Return all child coordinators for a config entry."""
    value = hass.data[DOMAIN][entry_id]
    if isinstance(value, list):
        return value
    return [value]
