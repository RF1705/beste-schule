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
from .entity import besteschule_device_info, school_name_from_data

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
TIMETABLE_CACHE_DAYS = 21


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
            BesteSchuleHomeworkCalendar(entry, coordinator),
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


def _teacher_text(value: Any) -> str | None:
    """Return a teacher name with forename when available."""
    if isinstance(value, list):
        parts = [_teacher_text(item) for item in value]
        return ", ".join(part for part in parts if part) or None

    if isinstance(value, dict):
        forename = _extract_text(value.get("forename"))
        name = _extract_text(value.get("name"))
        if forename or name:
            return " ".join(part for part in (forename, name) if part)

    return _extract_text(value)


def _room_text(value: Any) -> str | None:
    """Return a room label, preferring the school's local room number."""
    if isinstance(value, list):
        parts = [_room_text(item) for item in value]
        return ", ".join(part for part in parts if part) or None

    if isinstance(value, dict):
        for key in ("local_id", "name", "title", "label"):
            text = _extract_text(value.get(key))
            if text:
                return text

    return _extract_text(value)


def _find_nested_relation_text(
    item: dict[str, Any],
    keys: tuple[str, ...],
    formatter: Any,
) -> str | None:
    """Find formatted relation text for any key anywhere below the item."""
    for key in keys:
        text = formatter(item.get(key))
        if text:
            return text

    for value in item.values():
        if isinstance(value, dict):
            text = _find_nested_relation_text(value, keys, formatter)
            if text:
                return text
        elif isinstance(value, list):
            for nested in value:
                if isinstance(nested, dict):
                    text = _find_nested_relation_text(nested, keys, formatter)
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
        if 1 <= weekday <= 7:
            return weekday - 1
        if weekday == 0:
            return 0

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

        default_times = [timeset for timeset in times if isinstance(timeset, dict) and timeset.get("default")]
        for timeset in [*default_times, *times]:
            if not isinstance(timeset, dict):
                continue

            lessons = timeset.get("lessons")
            if not isinstance(lessons, list):
                continue

            for period in lessons:
                if not isinstance(period, dict):
                    continue

                number = _find_value(period, LESSON_NR_KEYS + ("lesson", "period"))
                start_time = _parse_time(_find_value(period, START_KEYS))
                end_time = _parse_time(_find_value(period, END_KEYS))
                if number is None or start_time is None or end_time is None:
                    continue

                try:
                    period_map.setdefault(int(number), (start_time, end_time))
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


def _all_text(value: Any) -> str:
    """Return searchable text for nested values."""
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_all_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_all_text(item) for item in value)
    return ""


def _substitution_overlay(data: dict[str, Any]) -> dict[tuple[date, int], dict[str, str | None]]:
    """Return cancellation/substitution markers keyed by date and lesson number."""
    overlay: dict[tuple[date, int], dict[str, str | None]] = {}
    source = data.get("substitution_days")
    for item in _iter_values(source):
        if not isinstance(item, dict):
            continue

        day = _parse_date(_find_value(item, DATE_KEYS))
        number = _find_value(item, LESSON_NR_KEYS)
        if day is None or number is None:
            continue

        text = _all_text(item).lower()
        try:
            key = (day, int(number))
        except (TypeError, ValueError):
            continue

        status = str(item.get("status", "")).lower()
        if (
            status in {"cancelled", "canceled", "ausfall", "free"}
            or any(marker in text for marker in ("ausfall", "entfällt", "entfaellt", "cancel"))
        ):
            overlay[key] = {"status": "cancelled"}
        elif status in {"substitution", "vertretung"} or any(
            marker in text for marker in ("vertret", "ersatz", "substitution")
        ):
            overlay[key] = {
                "status": "substitution",
                "title": _find_nested_text(item, TITLE_KEYS),
                "location": _find_nested_relation_text(item, ROOM_KEYS, _room_text),
                "teacher": _find_nested_relation_text(item, TEACHER_KEYS, _teacher_text),
                "notes": _extract_text(item.get("notes")),
            }
    return overlay


def _lesson_events(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Convert timetable-like API data into HA calendar events."""
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    period_map = _period_time_map(data)
    overlay = _substitution_overlay(data)
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

        number = _find_value(item, LESSON_NR_KEYS)
        location = _find_nested_relation_text(item, ROOM_KEYS, _room_text)
        teacher = _find_nested_relation_text(item, TEACHER_KEYS, _teacher_text)
        school_name = school_name_from_data(data)
        description_parts = []
        if location:
            description_parts.append(f"Raum: {location}")
        if teacher:
            description_parts.append(f"Lehrer: {teacher}")
        description = "\n".join(description_parts) or None

        if lesson_date:
            lesson_dates = [lesson_date]
        else:
            lesson_dates = []
            current_day = _date_for_weekday(start_date.date(), weekday)
            while current_day <= end_date.date():
                lesson_dates.append(current_day)
                current_day += timedelta(days=7)

        for current_day in lesson_dates:
            try:
                overlay_value = overlay.get((current_day, int(number)))
            except (TypeError, ValueError):
                overlay_value = None
            overlay_status = overlay_value.get("status") if overlay_value else None
            if overlay_status == "cancelled":
                continue

            event_start = datetime.combine(current_day, start_time, start_date.tzinfo)
            event_end = datetime.combine(current_day, end_time, start_date.tzinfo)
            if event_end > start_date and event_start < end_date:
                key = _event_key(current_day, start_time, end_time, title, location)
                if key not in seen:
                    seen.add(key)
                    substitution_title = overlay_value.get("title") if overlay_value else None
                    summary = substitution_title or title
                    event_description = description
                    if overlay_status == "substitution":
                        substitution_location = overlay_value.get("location") if overlay_value else None
                        substitution_teacher = overlay_value.get("teacher") if overlay_value else None
                        substitution_notes = overlay_value.get("notes") if overlay_value else None
                        event_description = "\n".join(
                            part
                            for part in (
                                f"Vertretung für: {title}",
                                f"Raum: {substitution_location}" if substitution_location else None,
                                f"Lehrer: {substitution_teacher}" if substitution_teacher else None,
                                substitution_notes,
                            )
                            if part
                        )
                    events.append(
                        CalendarEvent(
                            summary=summary,
                            start=event_start,
                            end=event_end,
                            location=school_name or location,
                            description=event_description,
                        )
                    )

    events.sort(key=lambda event: event.start)
    return events


def _cached_lesson_events(
    coordinator: BesteSchuleDataUpdateCoordinator,
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Return timetable events from an in-memory rolling cache."""
    now = dt_util.now()
    cache_start = getattr(coordinator, "timetable_cache_start", None)
    if cache_start is None:
        cache_start = now
        coordinator.timetable_cache_start = cache_start

    horizon = now + timedelta(days=TIMETABLE_CACHE_DAYS)
    cache: dict[str, CalendarEvent] = getattr(coordinator, "timetable_event_cache", {})
    if not hasattr(coordinator, "timetable_event_cache"):
        coordinator.timetable_event_cache = cache

    refresh_start = max(cache_start, now.replace(hour=0, minute=0, second=0, microsecond=0))
    if refresh_start < horizon:
        cache_keys = [
            key
            for key, event in cache.items()
            if event.start >= refresh_start and event.start < horizon
        ]
        for key in cache_keys:
            cache.pop(key, None)

        for event in _lesson_events(coordinator.data, refresh_start, horizon):
            cache[_cache_key(event)] = event

    visible_start = max(start_date, cache_start)
    visible_end = min(end_date, horizon)
    if visible_start >= visible_end:
        return []

    events = [
        event
        for event in cache.values()
        if event.end > visible_start and event.start < visible_end
    ]
    events.sort(key=lambda event: event.start)
    return events


def _cache_key(event: CalendarEvent) -> str:
    """Build a stable cache key for one lesson slot."""
    return f"{event.start.isoformat()}|{event.end.isoformat()}"


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


def _homework_events(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Convert visible homework journal notes into all-day calendar events."""
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    school_name = school_name_from_data(data)

    for source_key in ("journal_weeks", "journal_lesson_student"):
        for item in _iter_values(data.get(source_key)):
            if not isinstance(item, dict):
                continue

            note_date = _note_date(item)
            notes = item.get("notes")
            if note_date is None or not isinstance(notes, list):
                continue

            subject = _find_nested_text(
                item,
                ("subject", "subjects", "subjectName", "subject_name"),
            )
            for note in notes:
                if not isinstance(note, dict) or not _is_homework_note(note):
                    continue

                description = _extract_text(note.get("description"))
                title = _homework_title(subject, description)
                event_start = note_date
                event_end = note_date + timedelta(days=1)
                if event_end <= start_date.date() or event_start >= end_date.date():
                    continue

                key = f"{note_date.isoformat()}|{note.get('id')}|{title}|{description or ''}"
                if key in seen:
                    continue
                seen.add(key)
                events.append(
                    CalendarEvent(
                        summary=title,
                        start=event_start,
                        end=event_end,
                        location=school_name,
                        description=description,
                    )
                )

    events.sort(key=lambda event: event.start)
    return events


def _note_date(item: dict[str, Any]) -> date | None:
    """Find the date a journal note belongs to."""
    found = _parse_date(_find_value(item, DATE_KEYS))
    if found:
        return found

    for key in ("day", "lesson", "notable"):
        value = item.get(key)
        if isinstance(value, dict):
            found = _note_date(value)
            if found:
                return found

    return None


def _is_homework_note(note: dict[str, Any]) -> bool:
    """Return whether a journal note looks like homework."""
    text = _all_text(
        {
            "type": note.get("type"),
            "description": note.get("description"),
        }
    ).lower()
    return "hausauf" in text or "homework" in text


def _homework_title(subject: str | None, description: str | None) -> str:
    """Return a concise homework event title."""
    if subject:
        return f"Hausaufgabe: {subject}"
    if description:
        first_line = description.splitlines()[0].strip()
        if first_line:
            return first_line[:80]
    return "Hausaufgabe"


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
        events = _cached_lesson_events(
            self.coordinator,
            now,
            now + timedelta(days=TIMETABLE_CACHE_DAYS),
        )
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return _cached_lesson_events(self.coordinator, start_date, end_date)


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


class BesteSchuleHomeworkCalendar(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], CalendarEntity
):
    """Calendar for visible beste.schule homework entries."""

    _attr_has_entity_name = True
    _attr_translation_key = "homework"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_homework"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        events = _homework_events(self.coordinator.data, now, now + timedelta(days=60))
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return _homework_events(self.coordinator.data, start_date, end_date)
