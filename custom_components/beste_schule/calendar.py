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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule calendars."""
    coordinator: BesteSchuleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BesteSchuleCalendar(entry, coordinator)])


def _iter_values(value: Any) -> Iterable[Any]:
    """Yield all nested dicts/lists from a response."""
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_values(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_values(item)


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

    for item in _iter_values(data):
        if not isinstance(item, dict):
            continue

        weekday = _parse_weekday(_find_value(item, WEEKDAY_KEYS))
        start_time = _parse_time(_find_value(item, START_KEYS))
        end_time = _parse_time(_find_value(item, END_KEYS))
        if weekday is None or start_time is None or end_time is None:
            continue

        title = _find_nested_text(item, TITLE_KEYS)
        if not title:
            continue

        location = _find_nested_text(item, ROOM_KEYS)
        teacher = _find_nested_text(item, TEACHER_KEYS)
        description = teacher

        current_day = _date_for_weekday(start_date.date(), weekday)
        while current_day <= end_date.date():
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
            current_day += timedelta(days=7)

    events.sort(key=lambda event: event.start)
    return events


class BesteSchuleCalendar(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], CalendarEntity
):
    """Calendar for beste.schule timetable entries."""

    _attr_has_entity_name = True
    _attr_translation_key = "calendar"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="beste.schule",
            name=entry.title,
            configuration_url="https://beste.schule",
        )

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
