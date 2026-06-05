"""Calendar support for beste.schule."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
import re
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import besteschule_device_info

WEEKDAY_NAMES = {
    "monday": 0,
    "montag": 0,
    "mo": 0,
    "tuesday": 1,
    "dienstag": 1,
    "di": 1,
    "wednesday": 2,
    "mittwoch": 2,
    "mi": 2,
    "thursday": 3,
    "donnerstag": 3,
    "do": 3,
    "friday": 4,
    "freitag": 4,
    "fr": 4,
    "saturday": 5,
    "samstag": 5,
    "sa": 5,
    "sunday": 6,
    "sonntag": 6,
    "so": 6,
}

WEEKDAY_KEYS = (
    "weekday",
    "weekDay",
    "week_day",
    "dayOfWeek",
    "day_of_week",
    "day",
    "weekday_id",
)
DATE_KEYS = (
    "date",
    "day_date",
    "lesson_date",
    "starts_on",
    "start_date",
    "given_at",
)
START_KEYS = (
    "start",
    "starts_at",
    "start_at",
    "startTime",
    "start_time",
    "time_start",
    "from",
    "begin",
    "begins_at",
)
END_KEYS = (
    "end",
    "ends_at",
    "end_at",
    "endTime",
    "end_time",
    "time_end",
    "to",
    "until",
)
LESSON_NR_KEYS = ("nr", "number", "lessonNr", "lesson_nr", "lessonNumber")
TITLE_KEYS = (
    "subject",
    "subjects",
    "subjectName",
    "subject_name",
    "course",
    "lesson",
    "name",
    "title",
)
ROOM_KEYS = ("room", "rooms", "roomName", "room_name")
TEACHER_KEYS = ("teacher", "teachers", "teacherName", "teacher_name")
TIMETABLE_SOURCE_KEYS = (
    "time_tables_current",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule calendars."""
    coordinator: BesteSchuleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BesteSchuleTimetableCalendar(entry, coordinator),
            BesteSchuleAbsenceCalendar(entry, coordinator),
        ]
    )


def _iter_values(value: Any) -> Iterable[dict[str, Any]]:
    """Yield all nested dicts/lists from a response with inherited date context."""
    yield from _iter_values_with_context(value, {})


def _iter_values_with_context(
    value: Any,
    context: dict[str, Any],
) -> Iterable[dict[str, Any]]:
    """Yield nested dicts while carrying useful parent fields."""
    if isinstance(value, dict):
        item = {**context, **value}
        yield item
        next_context = dict(context)
        for key in DATE_KEYS + WEEKDAY_KEYS:
            if key in value and key not in next_context:
                next_context[key] = value[key]
        for nested in value.values():
            yield from _iter_values_with_context(nested, next_context)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_values_with_context(item, context)


def _extract_text(value: Any) -> str | None:
    """Extract a readable text value from common relation shapes."""
    if isinstance(value, str):
        return value.strip() or None

    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return ", ".join(part for part in parts if part) or None

    if isinstance(value, dict):
        for key in (
            "shortName",
            "short_name",
            "abbreviation",
            "displayName",
            "display_name",
            "fullName",
            "full_name",
            "name",
            "title",
            "label",
        ):
            text = _extract_text(value.get(key))
            if text:
                return text

        first_name = _extract_text(
            value.get("firstName") or value.get("first_name") or value.get("firstname")
        )
        last_name = _extract_text(
            value.get("lastName") or value.get("last_name") or value.get("lastname")
        )
        if first_name or last_name:
            return " ".join(part for part in (first_name, last_name) if part)

    return None


def _find_text(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Find text for any key at the current level."""
    for key in keys:
        text = _extract_text(item.get(key))
        if text:
            return text
    return None


def _find_nested_text(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Find text for any key anywhere below the item."""
    text = _find_text(item, keys)
    if text:
        return text

    for value in item.values():
        if isinstance(value, dict):
            text = _find_nested_text(value, keys)
            if text:
                return text
        elif isinstance(value, list):
            for nested in value:
                if isinstance(nested, dict):
                    text = _find_nested_text(nested, keys)
                    if text:
                        return text
    return None


def _find_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Find a scalar value for any key anywhere below the item."""
    for key in keys:
        value = item.get(key)
        if isinstance(value, (str, int, float)):
            return value

    for value in item.values():
        if isinstance(value, dict):
            found = _find_value(value, keys)
            if found is not None:
                return found
    return None


def _parse_weekday(value: Any) -> int | None:
    """Parse a weekday into Python's Monday=0 format."""
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in WEEKDAY_NAMES:
            return WEEKDAY_NAMES[cleaned]
        if cleaned.isdigit():
            value = int(cleaned)
        else:
            return None

    if isinstance(value, (int, float)):
        weekday = int(value)
        if 0 <= weekday <= 6:
            return weekday
        if 1 <= weekday <= 7:
            return weekday - 1

    return None


def _parse_time(value: Any) -> time | None:
    """Parse a time value from common API formats."""
    if isinstance(value, str):
        match = re.search(r"(\d{1,2}):(\d{2})", value)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour=hour, minute=minute)
    return None


def _period_time_map(data: dict[str, Any]) -> dict[int, tuple[time, time]]:
    """Build a lesson-number to start/end time map from school timetable times."""
    period_map: dict[int, tuple[time, time]] = {}
    for item in _iter_values(data.get("school")):
        times = item.get("times") if isinstance(item, dict) else None
        if not isinstance(times, list):
            continue

        for period in times:
            if not isinstance(period, dict):
                continue

            number = _find_value(period, LESSON_NR_KEYS + ("lesson", "period"))
            start_time = _parse_time(_find_value(period, START_KEYS))
            end_time = _parse_time(_find_value(period, END_KEYS))
            if number is None or start_time is None or end_time is None:
                continue

            try:
                period_map[int(number)] = (start_time, end_time)
            except (TypeError, ValueError):
                continue

    return period_map


def _parse_date(value: Any) -> date | None:
    """Parse a date value from common API formats."""
    if isinstance(value, str):
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
        if match:
            return date(
                year=int(match.group(1)),
                month=int(match.group(2)),
                day=int(match.group(3)),
            )
    return None


def _date_for_weekday(start_date: date, weekday: int) -> date:
    """Return the first date at or after start_date matching weekday."""
    return start_date + timedelta(days=(weekday - start_date.weekday()) % 7)


def _event_key(day: date, start: time, end: time, title: str, location: str | None) -> str:
    """Build a stable duplicate-detection key."""
    return f"{day.isoformat()}|{start.isoformat()}|{end.isoformat()}|{title}|{location or ''}"


def _lesson_events(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Convert timetable-like API data into HA calendar events."""
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    period_map = _period_time_map(data)
    source_data = {
        key: value
        for key, value in data.items()
        if key in TIMETABLE_SOURCE_KEYS and not (isinstance(value, dict) and "error" in value)
    }

    for item in _iter_values(source_data):
        if not isinstance(item, dict):
            continue

        lesson_date = _parse_date(_find_value(item, DATE_KEYS))
        weekday = _parse_weekday(_find_value(item, WEEKDAY_KEYS))
        start_time = _parse_time(_find_value(item, START_KEYS))
        end_time = _parse_time(_find_value(item, END_KEYS))
        if start_time is None or end_time is None:
            number = _find_value(item, LESSON_NR_KEYS)
            try:
                start_time, end_time = period_map[int(number)]
            except (KeyError, TypeError, ValueError):
                pass
        if (lesson_date is None and weekday is None) or start_time is None or end_time is None:
            continue

        title = _find_nested_text(item, TITLE_KEYS)
        if not title:
            continue

        location = _find_nested_text(item, ROOM_KEYS)
        teacher = _find_nested_text(item, TEACHER_KEYS)
        description = teacher

        if lesson_date:
            lesson_dates = [lesson_date]
        else:
            lesson_dates = []
            current_day = _date_for_weekday(start_date.date(), weekday)
            while current_day <= end_date.date():
                lesson_dates.append(current_day)
                current_day += timedelta(days=7)

        for current_day in lesson_dates:
            event_start = datetime.combine(current_day, start_time, start_date.tzinfo)
            event_end = datetime.combine(current_day, end_time, start_date.tzinfo)
            if event_end > start_date and event_start < end_date:
                key = _event_key(current_day, start_time, end_time, title, location)
                if key not in seen:
                    seen.add(key)
                    events.append(
                        CalendarEvent(
                            summary=title,
                            start=event_start,
                            end=event_end,
                            location=location,
                            description=description,
                        )
                    )

    events.sort(key=lambda event: event.start)
    return events


def _absence_text(value: Any) -> str | None:
    """Extract absence text from common absence shapes."""
    text = _extract_text(value)
    if text:
        return text
    if isinstance(value, dict):
        for key in ("reason", "type", "status", "name", "title"):
            text = _extract_text(value.get(key))
            if text:
                return text
    return None


def _absence_events(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Convert day-student absence data into all-day calendar events."""
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    source = data.get("journal_day_student")

    for item in _iter_values(source):
        if not isinstance(item, dict):
            continue

        lesson_date = _parse_date(_find_value(item, DATE_KEYS))
        if lesson_date is None:
            continue

        absent = item.get("present") == 0 or bool(item.get("absence"))
        if not absent:
            continue

        event_start = lesson_date
        event_end = lesson_date + timedelta(days=1)
        if event_end <= start_date.date() or event_start >= end_date.date():
            continue

        reason = _absence_text(item.get("absence")) or "Abwesend"
        key = f"{lesson_date.isoformat()}|absence"
        if key in seen:
            continue
        seen.add(key)
        events.append(
            CalendarEvent(
                summary=reason,
                start=event_start,
                end=event_end,
            )
        )

    events.sort(key=lambda event: event.start)
    return events


class BesteSchuleTimetableCalendar(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], CalendarEntity
):
    """Calendar for beste.schule timetable entries."""

    _attr_has_entity_name = True
    _attr_translation_key = "timetable"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_timetable"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        events = _lesson_events(self.coordinator.data, now, now + timedelta(days=14))
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return _lesson_events(self.coordinator.data, start_date, end_date)


class BesteSchuleAbsenceCalendar(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], CalendarEntity
):
    """Calendar for beste.schule absence entries."""

    _attr_has_entity_name = True
    _attr_translation_key = "absences"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_absences"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        events = _absence_events(self.coordinator.data, now, now + timedelta(days=60))
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return _absence_events(self.coordinator.data, start_date, end_date)
