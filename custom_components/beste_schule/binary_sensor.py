"""Binary sensors for beste.schule."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .calendar import _absence_events, _lesson_events
from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import (
    besteschule_device_info,
    school_address_from_data,
    school_coordinates_from_data,
    school_name_from_data,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule binary sensors."""
    coordinator: BesteSchuleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BesteSchuleAtSchoolBinarySensor(entry, coordinator)])


class BesteSchuleAtSchoolBinarySensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], BinarySensorEntity
):
    """Indicate whether the student is currently in school according to timetable."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_has_entity_name = True
    _attr_translation_key = "at_school"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_at_school"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def is_on(self) -> bool:
        """Return whether a lesson is currently active and no absence covers today."""
        now = dt_util.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        if _absence_events(self.coordinator.data, today_start, tomorrow_start):
            return False

        return any(
            event.start <= now < event.end
            for event in _lesson_events(
                self.coordinator.data,
                now - timedelta(minutes=1),
                now + timedelta(minutes=1),
            )
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return current lesson details."""
        now = dt_util.now()
        current = next(
            (
                event
                for event in _lesson_events(
                    self.coordinator.data,
                    now - timedelta(minutes=1),
                    now + timedelta(minutes=1),
                )
                if event.start <= now < event.end
            ),
            None,
        )
        attributes: dict[str, str | float | None] = {
            "current_lesson": current.summary if current else None,
            "current_location": current.location if current else None,
            "current_start": current.start.isoformat() if current else None,
            "current_end": current.end.isoformat() if current else None,
            "school": school_name_from_data(self.coordinator.data),
            "school_address": school_address_from_data(self.coordinator.data),
        }
        coordinates = school_coordinates_from_data(self.coordinator.data)
        if coordinates:
            attributes["latitude"] = coordinates[0]
            attributes["longitude"] = coordinates[1]
        return attributes
