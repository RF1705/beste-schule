"""Binary sensors for beste.schule."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import besteschule_device_info
from .presence import current_lesson, is_at_school


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
    _attr_translation_key = "school_time"

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
        return is_at_school(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return current lesson details."""
        current = current_lesson(self.coordinator)
        return {
            "current_lesson": current.summary if current else None,
            "current_location": current.location if current else None,
            "current_start": current.start.isoformat() if current else None,
            "current_end": current.end.isoformat() if current else None,
        }
