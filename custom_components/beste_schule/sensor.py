"""Sensors for beste.schule."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .calendar import (
    DATE_KEYS,
    TIMETABLE_CACHE_DAYS,
    _absence_text,
    _cached_lesson_events,
    _find_value,
    _iter_values,
    _parse_date,
)
from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import besteschule_device_info

CLASSWORK_MARKERS = (
    "ka",
    "klassenarbeit",
    "klassenarbeiten",
    "arbeit",
    "testat",
    "schulaufgabe",
    "klausur",
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
            BesteSchuleSickDaysSensor(entry, coordinator),
            BesteSchuleClassSensor(entry, coordinator),
            BesteSchuleTimetableCardSensor(entry, coordinator),
            BesteSchuleLessonSensor(entry, coordinator, "current_lesson"),
            BesteSchuleLessonSensor(entry, coordinator, "next_lesson"),
            *[
                BesteSchuleGradeAverageSensor(entry, coordinator, subject)
                for subject in _grade_subjects(coordinator.data)
            ],
        ]
    )


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
    """Parse a German numeric school grade, ignoring plus/minus modifiers."""
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

    return float(match.group(1))


def _parse_decimal(value: Any) -> float | None:
    """Parse decimal values using comma or dot."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "average", "avg", "calculation"):
            parsed = _parse_decimal(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if not isinstance(value, str):
        return None

    match = re.search(r"\d+(?:[,.]\d+)?", value)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def _api_average(data: dict[str, Any], subject: str) -> float | None:
    """Return an API-provided average for a subject, if available."""
    for item in _data_list(data.get("finalgrades")):
        if not isinstance(item, dict) or _subject_name(item) != subject:
            continue
        for key in (
            "value_calc",
            "value_calc_int",
            "average",
            "avg",
            "calculation",
            "calculated",
            "calculation_verbal",
            "final_value",
        ):
            value = _parse_decimal(item.get(key))
            if value is not None and 1 <= value <= 6:
                return value
    return None


def _grade_kind_text(grade: dict[str, Any]) -> str:
    """Return searchable text describing the grade type."""
    values: list[str] = []
    for key in (
        "type",
        "grade_type",
        "gradeType",
        "category",
        "collection",
        "local_id",
        "localId",
        "abbreviation",
        "calculation_for",
        "name",
        "title",
        "comment",
        "description",
    ):
        value = grade.get(key)
        if key == "collection" and isinstance(value, dict):
            for nested_key in (
                "type",
                "grade_type",
                "gradeType",
                "category",
                "local_id",
                "localId",
                "abbreviation",
                "name",
                "shortName",
                "short_name",
                "title",
                "value",
                "comment",
                "description",
            ):
                text = _text_value(value.get(nested_key))
                if text:
                    values.append(text)
            continue

        text = _text_value(value)
        if text:
            values.append(text)
    return " ".join(values).lower()


def _is_classwork(grade: dict[str, Any]) -> bool:
    """Return whether a grade should count as classwork."""
    words = set(re.findall(r"[a-zäöüß]+", _grade_kind_text(grade)))
    return any(marker in words for marker in CLASSWORK_MARKERS)


def _average(values: list[float]) -> float | None:
    """Return the average of values."""
    if not values:
        return None
    return sum(values) / len(values)


def _weighted_grade_average(
    classwork_values: list[float],
    other_values: list[float],
) -> float | None:
    """Return average with every classwork grade counted twice."""
    weighted_count = (len(classwork_values) * 2) + len(other_values)
    if weighted_count == 0:
        return None
    weighted_sum = (sum(classwork_values) * 2) + sum(other_values)
    return weighted_sum / weighted_count


def _school_round(value: float, classwork_average: float | None, other_average: float | None) -> int:
    """Round a school grade, resolving .5 towards the classwork average."""
    lower = int(value)
    fraction = value - lower
    if (
        abs(fraction - 0.5) < 0.00001
        and classwork_average is not None
        and other_average is not None
    ):
        if classwork_average < other_average:
            return lower
        if classwork_average > other_average:
            return lower + 1
    return int(value + 0.5)


def _subject_grade_values(
    data: dict[str, Any],
    subject: str,
) -> tuple[list[float], list[float]]:
    """Return classwork and other grade values for one subject."""
    classwork_values: list[float] = []
    other_values: list[float] = []
    for item in _data_list(data.get("grades")):
        if not isinstance(item, dict) or _subject_name(item) != subject:
            continue
        value = _parse_grade(item.get("value"))
        if value is None:
            continue
        if _is_classwork(item):
            classwork_values.append(value)
        else:
            other_values.append(value)
    return classwork_values, other_values


def _grade_subjects(data: dict[str, Any]) -> list[str]:
    """Return subjects with at least one parseable grade."""
    subjects: set[str] = set()
    for item in _data_list(data.get("grades")):
        if not isinstance(item, dict) or _parse_grade(item.get("value")) is None:
            continue
        subject = _subject_name(item)
        if subject:
            subjects.add(subject)
    for item in _data_list(data.get("finalgrades")):
        if not isinstance(item, dict):
            continue
        subject = _subject_name(item)
        if subject and _api_average(data, subject) is not None:
            subjects.add(subject)
    return sorted(subjects)


def _slug(value: str) -> str:
    """Return a simple slug for unique ids."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower())
    return slug.strip("_") or "unknown"


def _sick_absence_days(data: dict[str, Any]) -> set[str]:
    """Return all absence dates that look like sick days."""
    days: set[str] = set()
    for item in _iter_values(data.get("journal_day_student")):
        if not isinstance(item, dict):
            continue

        lesson_date = _parse_date(_find_value(item, DATE_KEYS))
        if lesson_date is None:
            continue

        absent = item.get("present") == 0 or bool(item.get("absence"))
        if not absent:
            continue

        reason = (_absence_text(item.get("absence")) or "").lower()
        if "krank" in reason or "sick" in reason:
            days.add(lesson_date.isoformat())

    return days


def _student_data(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first student data dict."""
    students = data.get("students")
    if isinstance(students, dict):
        value = students.get("data")
        if isinstance(value, list):
            return next((item for item in value if isinstance(item, dict)), None)
        if isinstance(value, dict):
            return value
    if isinstance(students, list):
        return next((item for item in students if isinstance(item, dict)), None)
    return None


def _student_class(data: dict[str, Any]) -> str | None:
    """Return the student's main class name."""
    student = _student_data(data)
    if not isinstance(student, dict):
        return None

    groups = student.get("meta_groups")
    if isinstance(groups, list):
        main_groups = [
            group
            for group in groups
            if isinstance(group, dict) and group.get("meta") in (1, True)
        ]
        for group in [*main_groups, *groups]:
            if not isinstance(group, dict):
                continue
            text = _text_value(group.get("local_id")) or _text_value(group.get("name"))
            if text:
                return text

    for key in ("class", "class_name", "className", "group", "group_name"):
        text = _text_value(student.get(key))
        if text:
            return text
    return None


def _weekday_key(index: int) -> str:
    """Return stundenplan-card weekday keys."""
    return ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")[index]


def _event_cell_text(event: Any) -> str:
    """Return a compact stundenplan-card cell text for one lesson event."""
    parts = [event.summary]
    if event.description:
        parts.extend(
            line.strip()
            for line in event.description.splitlines()
            if line.strip()
        )
    return "\n".join(part for part in parts if part)


def _timetable_card_rows(
    coordinator: BesteSchuleDataUpdateCoordinator,
) -> list[dict[str, Any]]:
    """Return current-week rows compatible with fabel-smith/stundenplan-card."""
    now = dt_util.now()
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_end = week_start + timedelta(days=7)
    events = _cached_lesson_events(coordinator, week_start, week_end)
    rows: dict[tuple[str, str], dict[str, Any]] = {}

    for event in events:
        weekday = event.start.weekday()
        if weekday > 4:
            continue

        start = event.start.strftime("%H:%M")
        end = event.end.strftime("%H:%M")
        key = (start, end)
        row = rows.setdefault(
            key,
            {
                "time": f"{start}-{end}",
                "start": start,
                "end": end,
                "Mo": "",
                "Di": "",
                "Mi": "",
                "Do": "",
                "Fr": "",
            },
        )
        day_key = _weekday_key(weekday)
        cell = _event_cell_text(event)
        row[day_key] = f"{row[day_key]}\n\n{cell}".strip() if row[day_key] else cell

    return [
        rows[key]
        for key in sorted(rows)
    ]


def _timetable_card_days() -> list[str]:
    """Return stundenplan-card day columns."""
    return ["Mo", "Di", "Mi", "Do", "Fr"]


def _timetable_card_meta_days() -> list[str]:
    """Return current-week dates for stundenplan-card headers."""
    now = dt_util.now()
    week_start = now.date() - timedelta(days=now.weekday())
    return [
        (week_start + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(5)
    ]


class BesteSchuleClassSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Expose the student's main class."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:google-classroom"
    _attr_translation_key = "school_class"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_school_class"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> str | None:
        """Return the student's main class."""
        return _student_class(self.coordinator.data)


class BesteSchuleTimetableCardSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Expose timetable rows for fabel-smith/stundenplan-card."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:table-clock"
    _attr_translation_key = "timetable_card"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_timetable_card"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> int:
        """Return the number of timetable rows."""
        return len(_timetable_card_rows(self.coordinator))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return rows in formats consumed by stundenplan-card."""
        rows = _timetable_card_rows(self.coordinator)
        days = _timetable_card_days()
        meta = {"days": _timetable_card_meta_days()}
        return {
            "rows_table": rows,
            "rows_json": rows,
            "plan": rows,
            "days": days,
            "meta": meta,
            "meta_ha": meta,
            "no_plan": not rows,
        }


class BesteSchuleSickDaysSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Count known sick absence days."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-remove"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_translation_key = "sick_days"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_sick_days"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> int:
        """Return the number of known sick days."""
        return len(_sick_absence_days(self.coordinator.data))

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        """Return the dates counted by this sensor."""
        return {"dates": sorted(_sick_absence_days(self.coordinator.data))}


class BesteSchuleLessonSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Expose the current or next timetable lesson."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
        kind: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._kind = kind
        self._attr_translation_key = kind
        self._attr_unique_id = f"{entry.entry_id}_{kind}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> str | None:
        """Return the lesson summary."""
        event = self._event
        return event.summary if event else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return useful lesson details."""
        event = self._event
        return {
            "start": event.start.isoformat() if event else None,
            "end": event.end.isoformat() if event else None,
            "location": event.location if event else None,
            "description": event.description if event else None,
        }

    @property
    def _event(self) -> Any | None:
        """Return the selected lesson event."""
        now = dt_util.now()
        events = _cached_lesson_events(
            self.coordinator,
            now - timedelta(minutes=1),
            now + timedelta(days=TIMETABLE_CACHE_DAYS),
        )
        if self._kind == "current_lesson":
            return next((event for event in events if event.start <= now < event.end), None)
        return next((event for event in events if event.start > now), None)


class BesteSchuleGradeAverageSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Average grade sensor for one subject."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
        subject: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._subject = subject
        self._attr_name = f"Note {subject}"
        self._attr_unique_id = f"{entry.entry_id}_grade_average_{_slug(subject)}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> float | None:
        """Return the rounded subject grade."""
        api_average = _api_average(self.coordinator.data, self._subject)
        if api_average is not None:
            return round(api_average, 2)

        classwork_values, other_values = self._grouped_values
        classwork_average = _average(classwork_values)
        other_average = _average(other_values)

        calculated_average = _weighted_grade_average(classwork_values, other_values)

        if calculated_average is None:
            return None

        return round(calculated_average, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details for the grade average."""
        api_average = _api_average(self.coordinator.data, self._subject)
        classwork_values, other_values = self._grouped_values
        classwork_average = _average(classwork_values)
        other_average = _average(other_values)
        calculated_average = _weighted_grade_average(classwork_values, other_values)

        return {
            "subject": self._subject,
            "source": "api" if api_average is not None else "calculated",
            "api_average": round(api_average, 2) if api_average is not None else None,
            "count": len(classwork_values) + len(other_values),
            "classwork_count": len(classwork_values),
            "other_count": len(other_values),
            "classwork_average": round(classwork_average, 2) if classwork_average is not None else None,
            "other_average": round(other_average, 2) if other_average is not None else None,
            "calculated_average": round(calculated_average, 2) if calculated_average is not None else None,
            "rounded_grade": (
                _school_round(calculated_average, classwork_average, other_average)
                if calculated_average is not None
                else None
            ),
            "classwork_grades": classwork_values,
            "other_grades": other_values,
        }

    @property
    def _grouped_values(self) -> tuple[list[float], list[float]]:
        """Return all parseable grades grouped by type."""
        return _subject_grade_values(self.coordinator.data, self._subject)
