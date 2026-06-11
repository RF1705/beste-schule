"""Binary sensors for beste.schule."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator, coordinators_for_entry
from .entity import besteschule_device_info
from .presence import current_lesson, is_at_school, school_day_bounds


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule binary sensors."""
    async_add_entities(
        [
            BesteSchuleAtSchoolBinarySensor(entry, coordinator)
            for coordinator in coordinators_for_entry(hass, entry.entry_id)
        ]
    )


class BesteSchuleAtSchoolBinarySensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], BinarySensorEntity
):
    """Indicate whether the student is currently in school according to timetable."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_has_entity_name = True
    _attr_translation_key = "school_time"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.unique_id_prefix(entry.entry_id)}_at_school"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def is_on(self) -> bool:
        """Return whether the current time is inside today's school day."""
        return is_at_school(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return current lesson details."""
        current = current_lesson(self.coordinator)
        first_lesson, last_lesson = school_day_bounds(self.coordinator)
        attributes: dict[str, str] = {}
        if current is not None:
            attributes["current_lesson"] = current.summary
            if current.location:
                attributes["current_location"] = current.location
            attributes["current_start"] = current.start.isoformat()
            attributes["current_end"] = current.end.isoformat()
        if first_lesson is not None:
            attributes["school_day_start"] = first_lesson.start.isoformat()
        if last_lesson is not None:
            attributes["school_day_end"] = last_lesson.end.isoformat()
        return attributes
