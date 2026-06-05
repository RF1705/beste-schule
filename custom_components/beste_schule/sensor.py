"""Sensors for beste.schule."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator

TIMETABLE_KEYS = (
    "time_tables",
    "time_tables_current",
    "time_tables_show_current",
    "time_table_times",
    "time_table_time_lessons",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule sensors."""
    coordinator: BesteSchuleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BesteSchuleCountSensor(entry, coordinator, "announcements"),
            BesteSchuleCountSensor(entry, coordinator, "checklists"),
            BesteSchuleCountSensor(entry, coordinator, "grades"),
            BesteSchuleCountSensor(entry, coordinator, "finalgrades"),
            BesteSchuleTimetableDiagnosticsSensor(entry, coordinator),
        ]
    )


def _count_items(value: Any) -> int | None:
    """Return a useful count for common API response shapes."""
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        if isinstance(value.get("data"), list):
            return len(value["data"])
        if "error" in value:
            return None
    return None


def _response_status(value: Any) -> str:
    """Return a compact diagnostic status for an API response."""
    if isinstance(value, dict) and isinstance(value.get("error"), str):
        return value["error"]

    count = _count_items(value)
    if count is not None:
        return str(count)

    if value is None:
        return "missing"

    return type(value).__name__


class BesteSchuleCountSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Count items returned by a beste.schule route."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
        data_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = data_key
        self._attr_unique_id = f"{entry.entry_id}_{data_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="beste.schule",
            name=entry.title,
            configuration_url="https://beste.schule",
        )
        self._data_key = data_key

    @property
    def native_value(self) -> int | None:
        """Return the number of returned items, if available."""
        return _count_items(self.coordinator.data.get(self._data_key))


class BesteSchuleTimetableDiagnosticsSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Expose timetable route counts for setup diagnostics."""

    _attr_has_entity_name = True
    _attr_translation_key = "timetable_data"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_timetable_data"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="beste.schule",
            name=entry.title,
            configuration_url="https://beste.schule",
        )

    @property
    def native_value(self) -> int:
        """Return the total number of known timetable items."""
        return sum(
            count
            for key in TIMETABLE_KEYS
            if (count := _count_items(self.coordinator.data.get(key))) is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return per-route diagnostic statuses."""
        return {
            key: _response_status(self.coordinator.data.get(key))
            for key in TIMETABLE_KEYS
        }
