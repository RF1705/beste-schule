"""Sensors for beste.schule."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import besteschule_device_info

INTEGRATION_VERSION = "0.1.6"

TIMETABLE_KEYS = (
    "time_tables",
    "time_tables_current",
    "time_tables_show_current",
    "time_tables_show_current_kebab",
    "time_table_times",
    "time_table_time_lessons",
    "journal_days",
    "journal_weeks",
    "journal_lessons",
    "journal_lesson_student",
    "journal_day_student",
    "journal_lessons_student",
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
            *[
                BesteSchuleGradeAverageSensor(entry, coordinator, subject)
                for subject in _grade_subjects(coordinator.data)
            ],
        ]
    )


def _count_items(value: Any) -> int | None:
    """Return a useful count for common API response shapes."""
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        if isinstance(value.get("data"), list):
            return len(value["data"])
        for key in ("lessons", "times", "days", "weeks", "items"):
            if isinstance(value.get(key), list):
                return len(value[key])
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

    if isinstance(value, dict):
        keys = ", ".join(sorted(str(key) for key in value.keys())[:8])
        return f"dict: {keys}" if keys else "dict"

    return type(value).__name__


def _first_id(value: Any) -> str:
    """Return the first id found in common response shapes."""
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        return _first_id(value["data"])
    if isinstance(value, list):
        for item in value:
            found = _first_id(item)
            if found != "missing":
                return found
    if isinstance(value, dict):
        found = value.get("id")
        if isinstance(found, (int, str)):
            return str(found)
    return "missing"


def _school_status(value: Any) -> str:
    """Return a compact school diagnostic status."""
    if isinstance(value, dict) and isinstance(value.get("error"), str):
        return value["error"]
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, dict):
            name = data.get("name") or data.get("displayName") or data.get("display_name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        name = value.get("name") or value.get("displayName") or value.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return _response_status(value)


def _data_list(value: Any) -> list[Any]:
    """Return a data list from common API response shapes."""
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        return value["data"]
    if isinstance(value, list):
        return value
    return []


def _text_value(value: Any) -> str | None:
    """Return a readable text from common relation shapes."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "shortName", "short_name", "title", "value"):
            text = _text_value(value.get(key))
            if text:
                return text
    return None


def _subject_name(grade: dict[str, Any]) -> str | None:
    """Return the subject name for a grade item."""
    return _text_value(grade.get("subject")) or _text_value(grade.get("subject_name"))


def _parse_grade(value: Any) -> float | None:
    """Parse a German numeric school grade."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "grade", "name"):
            parsed = _parse_grade(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if not isinstance(value, str):
        return None

    match = re.search(r"([1-6])(?:([+-]))?", value.strip())
    if not match:
        return None

    grade = float(match.group(1))
    modifier = match.group(2)
    if modifier == "+":
        grade -= 0.25
    elif modifier == "-":
        grade += 0.25
    return grade


def _grade_subjects(data: dict[str, Any]) -> list[str]:
    """Return subjects with at least one parseable grade."""
    subjects: set[str] = set()
    for item in _data_list(data.get("grades")):
        if not isinstance(item, dict) or _parse_grade(item.get("value")) is None:
            continue
        subject = _subject_name(item)
        if subject:
            subjects.add(subject)
    return sorted(subjects)


def _slug(value: str) -> str:
    """Return a simple slug for unique ids."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower())
    return slug.strip("_") or "unknown"


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
        self._entry = entry
        self._data_key = data_key

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> int | None:
        """Return the number of returned items, if available."""
        return _count_items(self.coordinator.data.get(self._data_key))


class BesteSchuleGradeAverageSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Average grade sensor for one subject."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
        subject: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._subject = subject
        self._attr_name = f"{subject} Durchschnitt"
        self._attr_unique_id = f"{entry.entry_id}_grade_average_{_slug(subject)}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> float | None:
        """Return the grade average."""
        values = self._values
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details for the grade average."""
        values = self._values
        return {
            "subject": self._subject,
            "count": len(values),
            "grades": values,
        }

    @property
    def _values(self) -> list[float]:
        """Return all parseable grades for the subject."""
        values: list[float] = []
        for item in _data_list(self.coordinator.data.get("grades")):
            if not isinstance(item, dict) or _subject_name(item) != self._subject:
                continue
            value = _parse_grade(item.get("value"))
            if value is not None:
                values.append(value)
        return values


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
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

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
        attributes = {
            key: _response_status(self.coordinator.data.get(key))
            for key in TIMETABLE_KEYS
        }
        attributes["students_first_id"] = _first_id(self.coordinator.data.get("students"))
        attributes["school"] = _school_status(self.coordinator.data.get("school"))
        attributes["integration_version"] = INTEGRATION_VERSION
        return attributes
