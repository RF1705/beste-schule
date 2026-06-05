"""Device tracker for beste.schule."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_NOT_HOME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import (
    besteschule_device_info,
    school_address_from_data,
    school_coordinates_from_data,
    school_name_from_data,
)
from .presence import current_lesson, is_at_school


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule device trackers."""
    coordinator: BesteSchuleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BesteSchuleDeviceTracker(entry, coordinator)])


class BesteSchuleDeviceTracker(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], TrackerEntity
):
    """Track the student at school while timetable says school is active."""

    _attr_has_entity_name = True
    _attr_translation_key = "school_tracker"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_school_tracker"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude while in school."""
        coordinates = school_coordinates_from_data(self.coordinator.data)
        if not is_at_school(self.coordinator.data) or coordinates is None:
            return None
        return coordinates[0]

    @property
    def longitude(self) -> float | None:
        """Return longitude while in school."""
        coordinates = school_coordinates_from_data(self.coordinator.data)
        if not is_at_school(self.coordinator.data) or coordinates is None:
            return None
        return coordinates[1]

    @property
    def location_accuracy(self) -> int | None:
        """Return location accuracy in meters."""
        return 50 if is_at_school(self.coordinator.data) else None

    @property
    def location_name(self) -> str | None:
        """Return not_home while not in school."""
        return None if is_at_school(self.coordinator.data) else STATE_NOT_HOME

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return school and current lesson attributes."""
        lesson = current_lesson(self.coordinator.data)
        return {
            "school": school_name_from_data(self.coordinator.data),
            "school_address": school_address_from_data(self.coordinator.data),
            "current_lesson": lesson.summary if lesson else None,
            "current_start": lesson.start.isoformat() if lesson else None,
            "current_end": lesson.end.isoformat() if lesson else None,
        }
