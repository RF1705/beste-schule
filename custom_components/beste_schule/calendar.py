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
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLE_ABSENCE_CALENDAR,
    CONF_ENABLE_EXAM_CALENDAR,
    CONF_ENABLE_HOMEWORK_CALENDAR,
    CONF_ENABLE_NOTICE_CALENDAR,
    CONF_ENABLE_TIMETABLE_CALENDAR,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .coordinator import BesteSchuleDataUpdateCoordinator, coordinators_for_entry
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
TIMETABLE_HISTORY_STORE_VERSION = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule calendars."""
    options = {**DEFAULT_OPTIONS, **entry.options}
    entities: list[CalendarEntity] = []
    for coordinator in coordinators_for_entry(hass, entry.entry_id):
        if options[CONF_ENABLE_TIMETABLE_CALENDAR]:
            entities.append(BesteSchuleTimetableCalendar(entry, coordinator))
        if options[CONF_ENABLE_ABSENCE_CALENDAR]:
            entities.append(BesteSchuleAbsenceCalendar(entry, coordinator))
        if options[CONF_ENABLE_HOMEWORK_CALENDAR]:
            entities.append(BesteSchuleHomeworkCalendar(entry, coordinator))
        if options[CONF_ENABLE_EXAM_CALENDAR]:
            entities.append(BesteSchuleExamCalendar(entry, coordinator))
        if options[CONF_ENABLE_NOTICE_CALENDAR]:
            entities.append(BesteSchuleNoticeCalendar(entry, coordinator))
    async_add_entities(entities)


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


def _replacement_relation_text(value: Any, formatter: Any) -> str | None:
    """Return the replacement relation, usually the last item in a substitution list."""
    if isinstance(value, list) and len(value) > 1:
        return formatter(value[-1])
    return formatter(value)


def _relation_texts(value: Any, formatter: Any) -> list[str]:
    """Return formatted relation texts without joining list values."""
    if isinstance(value, list):
        return [text for item in value if (text := formatter(item))]
    text = formatter(value)
    return [text] if text else []


def _direct_relation_texts(
    item: dict[str, Any],
    keys: tuple[str, ...],
    formatter: Any,
) -> list[str]:
    """Return formatted relation texts from the current level only."""
    for key in keys:
        texts = _relation_texts(item.get(key), formatter)
        if texts:
            return texts
    return []


def _normalized_text(value: str | None) -> str | None:
    """Return text normalized for comparisons."""
    if not value:
        return None
    return " ".join(value.split()).casefold()


def _replacement_teacher_text(
    replacement_teachers: list[str],
    original_teacher: str | None,
) -> str | None:
    """Return the replacement teacher, excluding the original teacher when possible."""
    if not replacement_teachers:
        return None
    if len(replacement_teachers) == 1:
        return replacement_teachers[0]

    normalized_original = _normalized_text(original_teacher)
    for replacement_teacher in replacement_teachers:
        if _normalized_text(replacement_teacher) != normalized_original:
            return replacement_teacher
    return replacement_teachers[-1]


def _replacement_room_text(
    replacement_rooms: list[str],
    original_room: str | None,
) -> str | None:
    """Return the replacement room, excluding the original room when possible."""
    if not replacement_rooms:
        return None
    if len(replacement_rooms) == 1:
        return replacement_rooms[0]

    normalized_original = _normalized_text(original_room)
    for replacement_room in replacement_rooms:
        if _normalized_text(replacement_room) != normalized_original:
            return replacement_room
    return replacement_rooms[-1]


def _direct_relation_text(
    item: dict[str, Any],
    keys: tuple[str, ...],
    formatter: Any,
) -> str | None:
    """Return formatted relation text from the current level only."""
    for key in keys:
        text = formatter(item.get(key))
        if text:
            return text
    return None


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


def _find_direct_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Find a scalar value for any key at the current level only."""
    for key in keys:
        value = item.get(key)
        if isinstance(value, (str, int, float)):
            return value
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


def _timetable_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return the current timetable object from the API response."""
    timetable = data.get("time_tables_current")
    if isinstance(timetable, dict) and isinstance(timetable.get("data"), dict):
        return timetable["data"]
    return {}


def _timetable_no_school_dates(data: dict[str, Any]) -> set[date]:
    """Return dates where the current timetable explicitly says there is no school."""
    timetable = _timetable_data(data)
    values = timetable.get("no_school_dates")
    if not isinstance(values, list):
        return set()

    days: set[date] = set()
    for value in values:
        parsed = _parse_date(value)
        if parsed is not None:
            days.add(parsed)
    return days


def _timetable_valid_range(data: dict[str, Any]) -> tuple[date | None, date | None]:
    """Return the current timetable validity range."""
    timetable = _timetable_data(data)
    return (
        _parse_date(timetable.get("valid_from")),
        _parse_date(timetable.get("valid_to")),
    )


def _is_timetable_school_day(data: dict[str, Any], day: date) -> bool:
    """Return whether timetable events should be generated for a date."""
    valid_from, valid_to = _timetable_valid_range(data)
    if valid_from is not None and day < valid_from:
        return False
    if valid_to is not None and day > valid_to:
        return False
    return day not in _timetable_no_school_dates(data)


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


def _substitution_overlay(data: dict[str, Any]) -> dict[tuple[date, int], dict[str, Any]]:
    """Return cancellation/substitution markers keyed by date and lesson number."""
    overlay: dict[tuple[date, int], dict[str, Any]] = {}
    source = data.get("substitution_days")
    for item in _iter_values(source):
        if not isinstance(item, dict):
            continue

        number = _find_direct_value(item, LESSON_NR_KEYS)
        if number is None:
            continue

        day = _parse_date(_find_value(item, DATE_KEYS))
        if day is None or number is None:
            continue

        try:
            key = (day, int(number))
        except (TypeError, ValueError):
            continue

        status = str(item.get("status", "")).lower()
        if status in {"initial", "hold", "regular"}:
            continue
        text = _all_text(item.get("notes")).lower()
        if (
            status in {"cancelled", "canceled", "ausfall", "free"}
            or any(marker in text for marker in ("ausfall", "entfällt", "entfaellt", "cancel"))
        ):
            overlay[key] = {"status": "cancelled"}
        elif status in {"planned", "substitution", "vertretung"} or any(
            marker in text for marker in ("vertret", "ersatz", "substitution")
        ):
            overlay[key] = {
                "status": "substitution",
                "title": _find_text(item, TITLE_KEYS) or _find_nested_text(item, TITLE_KEYS),
                "location": _direct_relation_text(
                    item,
                    ROOM_KEYS,
                    lambda value: _replacement_relation_text(value, _room_text),
                ),
                "locations": _direct_relation_texts(item, ROOM_KEYS, _room_text),
                "teacher": _direct_relation_text(
                    item,
                    TEACHER_KEYS,
                    lambda value: _replacement_relation_text(value, _teacher_text),
                ),
                "teachers": _direct_relation_texts(item, TEACHER_KEYS, _teacher_text),
                "notes": _extract_text(item.get("notes")),
            }
        else:
            title = _find_text(item, TITLE_KEYS) or _find_nested_text(item, TITLE_KEYS)
            location = _direct_relation_text(
                item,
                ROOM_KEYS,
                lambda value: _replacement_relation_text(value, _room_text),
            )
            teacher = _direct_relation_text(
                item,
                TEACHER_KEYS,
                lambda value: _replacement_relation_text(value, _teacher_text),
            )
            notes = _extract_text(item.get("notes"))
            if title or location or teacher or notes:
                overlay[key] = {
                    "status": "substitution",
                    "title": title,
                    "location": location,
                    "locations": _direct_relation_texts(item, ROOM_KEYS, _room_text),
                    "teacher": teacher,
                    "teachers": _direct_relation_texts(item, TEACHER_KEYS, _teacher_text),
                    "notes": notes,
                }
    return overlay


def _lesson_events(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
    include_cancelled: bool = False,
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
            if not _is_timetable_school_day(data, current_day):
                continue

            try:
                overlay_value = overlay.get((current_day, int(number)))
            except (TypeError, ValueError):
                overlay_value = None
            overlay_status = overlay_value.get("status") if overlay_value else None
            if overlay_status == "cancelled":
                if not include_cancelled:
                    continue

            event_start = _local_datetime(current_day, start_time)
            event_end = _local_datetime(current_day, end_time)
            if event_end > start_date and event_start < end_date:
                key = _event_key(current_day, start_time, end_time, title, location)
                if key not in seen:
                    seen.add(key)
                    substitution_title = overlay_value.get("title") if overlay_value else None
                    summary = (
                        f"Ausfall: {title}"
                        if overlay_status == "cancelled"
                        else substitution_title or title
                    )
                    event_description = description
                    if overlay_status == "cancelled":
                        event_description = "\n".join(
                            part
                            for part in (
                                "Status: Ausfall",
                                description,
                            )
                            if part
                        )
                    if overlay_status == "substitution":
                        substitution_location = (
                            overlay_value.get("location") if overlay_value else None
                        )
                        substitution_locations = (
                            overlay_value.get("locations") if overlay_value else []
                        )
                        substitution_teacher = (
                            overlay_value.get("teacher") if overlay_value else None
                        )
                        substitution_teachers = (
                            overlay_value.get("teachers") if overlay_value else []
                        )
                        substitution_notes = (
                            overlay_value.get("notes") if overlay_value else None
                        )
                        if isinstance(substitution_teachers, list):
                            substitution_teacher = (
                                _replacement_teacher_text(substitution_teachers, teacher)
                                or substitution_teacher
                            )
                        if isinstance(substitution_locations, list):
                            substitution_location = (
                                _replacement_room_text(substitution_locations, location)
                                or substitution_location
                            )
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

    _apply_dated_substitution_lessons(
        data,
        events,
        start_date,
        end_date,
        period_map,
        include_cancelled,
    )
    events.sort(key=lambda event: _event_sort_value(event.start))
    return events


def _apply_dated_substitution_lessons(
    data: dict[str, Any],
    events: list[CalendarEvent],
    start_date: datetime,
    end_date: datetime,
    period_map: dict[int, tuple[time, time]],
    include_cancelled: bool,
) -> None:
    """Replace weekly-plan slots with authoritative dated substitution lessons."""
    source = data.get("substitution_days")
    days = source.get("data") if isinstance(source, dict) else source
    if not isinstance(days, list):
        return

    school_name = school_name_from_data(data)
    for day_item in days:
        if not isinstance(day_item, dict):
            continue
        lesson_date = _parse_date(day_item.get("date"))
        lessons = day_item.get("lessons")
        if lesson_date is None or not isinstance(lessons, list):
            continue

        for lesson in lessons:
            if not isinstance(lesson, dict):
                continue
            number = _find_direct_value(lesson, LESSON_NR_KEYS)
            try:
                start_time, end_time = period_map[int(number)]
            except (KeyError, TypeError, ValueError):
                continue

            event_start = _local_datetime(lesson_date, start_time)
            event_end = _local_datetime(lesson_date, end_time)
            if event_end <= start_date or event_start >= end_date:
                continue

            original = next(
                (
                    event
                    for event in events
                    if event.start == event_start and event.end == event_end
                ),
                None,
            )
            events[:] = [
                event
                for event in events
                if event.start != event_start or event.end != event_end
            ]

            title = _find_text(lesson, TITLE_KEYS) or _find_nested_text(
                lesson,
                TITLE_KEYS,
            )
            if not title:
                continue

            status = str(lesson.get("status", "")).lower()
            cancelled = status in {"cancelled", "canceled", "ausfall", "free"}
            if cancelled and not include_cancelled:
                continue

            location = _direct_relation_text(lesson, ROOM_KEYS, _room_text)
            teacher = _direct_relation_text(lesson, TEACHER_KEYS, _teacher_text)
            locations = _direct_relation_texts(lesson, ROOM_KEYS, _room_text)
            teachers = _direct_relation_texts(lesson, TEACHER_KEYS, _teacher_text)
            regular_lesson = _regular_lesson_for_slot(data, lesson_date, number)
            original_title = (
                _find_nested_text(regular_lesson, TITLE_KEYS)
                if regular_lesson is not None
                else None
            )
            original_location = (
                _find_nested_relation_text(regular_lesson, ROOM_KEYS, _room_text)
                if regular_lesson is not None
                else _description_value(original, "Raum")
            )
            original_teacher = (
                _find_nested_relation_text(regular_lesson, TEACHER_KEYS, _teacher_text)
                if regular_lesson is not None
                else _description_value(original, "Lehrer")
            )
            if status in {"planned", "substitution", "vertretung"}:
                location = _replacement_room_text(locations, original_location) or location
                teacher = _replacement_teacher_text(teachers, original_teacher) or teacher

            if cancelled:
                summary = f"Ausfall: {title}"
                description_parts = ["Status: Ausfall"]
            elif status in {"planned", "substitution", "vertretung"}:
                summary = title
                description_parts = [f"Vertretung für: {original_title or title}"]
            else:
                summary = title
                description_parts = []

            if location:
                description_parts.append(f"Raum: {location}")
            if teacher:
                description_parts.append(f"Lehrer: {teacher}")
            notes = _extract_text(lesson.get("notes"))
            if notes:
                description_parts.append(notes)

            events.append(
                CalendarEvent(
                    summary=summary,
                    start=event_start,
                    end=event_end,
                    location=school_name or location,
                    description="\n".join(description_parts) or None,
                )
            )


def _regular_lesson_for_slot(
    data: dict[str, Any],
    lesson_date: date,
    number: Any,
) -> dict[str, Any] | None:
    """Return the weekly-plan lesson for a concrete date and lesson number."""
    timetable = _timetable_data(data)
    lessons = timetable.get("lessons")
    if not isinstance(lessons, list):
        return None

    try:
        expected_number = int(number)
    except (TypeError, ValueError):
        return None

    for lesson in lessons:
        if not isinstance(lesson, dict):
            continue
        weekday = _parse_weekday(_find_direct_value(lesson, WEEKDAY_KEYS))
        lesson_number = _find_direct_value(lesson, LESSON_NR_KEYS)
        try:
            matches_number = int(lesson_number) == expected_number
        except (TypeError, ValueError):
            matches_number = False
        if weekday == lesson_date.weekday() and matches_number:
            return lesson
    return None


def _description_value(event: CalendarEvent | None, label: str) -> str | None:
    """Return a labelled value from an existing event description."""
    if event is None or not event.description:
        return None
    prefix = f"{label}:"
    for line in event.description.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip() or None
    return None


def _event_sort_value(value: date | datetime) -> datetime:
    """Return a datetime for sorting calendar events with mixed date types."""
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min)


def _local_datetime(day: date, value: time) -> datetime:
    """Return a timezone-aware datetime for a local school time."""
    timezone = getattr(dt_util, "DEFAULT_TIME_ZONE", None) or dt_util.now().tzinfo
    return datetime.combine(day, value, timezone)


def _cached_lesson_events(
    coordinator: BesteSchuleDataUpdateCoordinator,
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Return timetable events with frozen history and live future data."""
    now = dt_util.now()
    cache_start = getattr(coordinator, "timetable_cache_start", None)
    if cache_start is None:
        cache_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        coordinator.timetable_cache_start = cache_start

    horizon = now + timedelta(days=TIMETABLE_CACHE_DAYS)
    cache: dict[str, CalendarEvent] = getattr(coordinator, "timetable_event_cache", {})
    if not hasattr(coordinator, "timetable_event_cache"):
        coordinator.timetable_event_cache = cache

    visible_start = max(start_date, cache_start)
    visible_end = min(end_date, horizon)
    if visible_start >= visible_end:
        return []

    cutoff = _history_cutoff()
    live_start = max(visible_start, cutoff)
    live_keys = [
        key
        for key, event in cache.items()
        if event.start >= live_start and event.end > visible_start and event.start < visible_end
    ]
    for key in live_keys:
        cache.pop(key, None)

    if visible_start < cutoff:
        for event in _lesson_events(
            coordinator.data,
            visible_start,
            min(visible_end, cutoff),
        ):
            cache.setdefault(_cache_key(event), event)

    if live_start < visible_end:
        for event in _lesson_events(coordinator.data, live_start, visible_end):
            cache[_cache_key(event)] = event

    events = [
        event
        for event in cache.values()
        if event.end > visible_start and event.start < visible_end
    ]
    events.sort(key=lambda event: _event_sort_value(event.start))
    return events


def _cache_key(event: CalendarEvent) -> str:
    """Build a stable cache key for one lesson slot."""
    return f"{event.start.isoformat()}|{event.end.isoformat()}"


def _event_to_storage(event: CalendarEvent) -> dict[str, Any]:
    """Convert a calendar event to stored JSON data."""
    return {
        "summary": event.summary,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "location": event.location,
        "description": event.description,
    }


def _event_from_storage(value: dict[str, Any]) -> CalendarEvent | None:
    """Convert stored JSON data back to a calendar event."""
    summary = value.get("summary")
    start = _parse_stored_datetime(value.get("start"))
    end = _parse_stored_datetime(value.get("end"))
    if not isinstance(summary, str) or start is None or end is None:
        return None
    return CalendarEvent(
        summary=summary,
        start=start,
        end=end,
        location=_extract_text(value.get("location")),
        description=_extract_text(value.get("description")),
    )


def _parse_stored_datetime(value: Any) -> datetime | None:
    """Parse a stored datetime string."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return dt_util.as_local(parsed)
    return parsed


def _history_cutoff() -> datetime:
    """Return the point before which timetable events are frozen."""
    return dt_util.now()


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
    events = [
        CalendarEvent(
            summary=entry["title"],
            start=entry["date"],
            end=entry["date"] + timedelta(days=1),
            location=entry["location"],
            description=entry["description"],
        )
        for entry in _homework_entries(data, start_date, end_date)
    ]
    events.sort(key=lambda event: event.start)
    return events


def _notice_events(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Convert school-wide substitution day notes into all-day calendar events."""
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    school_name = school_name_from_data(data)
    for item in _iter_values(data.get("substitution_days")):
        if not isinstance(item, dict):
            continue

        if _find_direct_value(item, LESSON_NR_KEYS) is not None:
            continue

        notice_date = _parse_date(_find_value(item, DATE_KEYS))
        notes = item.get("notes")
        if notice_date is None or not isinstance(notes, list):
            continue

        event_start = notice_date
        event_end = notice_date + timedelta(days=1)
        if event_end <= start_date.date() or event_start >= end_date.date():
            continue

        for note in notes:
            text = _extract_text(note)
            if not text:
                continue
            key = f"{notice_date.isoformat()}|{text}"
            if key in seen:
                continue
            seen.add(key)
            events.append(
                CalendarEvent(
                    summary=text,
                    start=event_start,
                    end=event_end,
                    location=school_name,
                )
            )

    events.sort(key=lambda event: (event.start, event.summary))
    return events


def _homework_entries(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Return visible homework notes as stable internal items."""
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    school_name = school_name_from_data(data)

    for source_key in ("journal_lessons", "journal_weeks", "journal_lesson_student"):
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

                key = _homework_event_key(note, note_date, title, description)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(
                    {
                        "key": key,
                        "title": title,
                        "date": event_start,
                        "location": school_name,
                        "description": description,
                    }
                )

    entries.sort(key=lambda entry: (entry["date"], entry["title"]))
    return entries


def _homework_event_key(
    note: dict[str, Any],
    note_date: date,
    title: str,
    description: str | None,
) -> str:
    """Build a stable duplicate-detection key for homework notes."""
    note_id = note.get("id")
    description_key = " ".join((description or "").split())
    if description_key or title:
        return f"content:{note_date.isoformat()}|{title}|{description_key}"
    return f"note:{note_id}" if note_id is not None else f"date:{note_date.isoformat()}"


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


def _exam_events(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[CalendarEvent]:
    """Convert visible classwork journal notes into calendar events."""
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    school_name = school_name_from_data(data)
    period_map = _period_time_map(data)

    for entry in _exam_entries(data, start_date, end_date):
        key = entry["key"]
        if key in seen:
            continue
        seen.add(key)

        exam_date = entry["date"]
        number = entry["number"]
        start_time = entry["start_time"]
        end_time = entry["end_time"]
        if start_time is None or end_time is None:
            try:
                start_time, end_time = period_map[int(number)]
            except (KeyError, TypeError, ValueError):
                pass

        description_parts = []
        if entry["description"]:
            description_parts.append(entry["description"])
        if entry["room"]:
            description_parts.append(f"Raum: {entry['room']}")
        if entry["teacher"]:
            description_parts.append(f"Lehrer: {entry['teacher']}")
        if entry["note_type"]:
            description_parts.append(f"Typ: {entry['note_type']}")

        if start_time is not None and end_time is not None:
            event_start: date | datetime = _local_datetime(exam_date, start_time)
            event_end: date | datetime = _local_datetime(exam_date, end_time)
        else:
            event_start = exam_date
            event_end = exam_date + timedelta(days=1)

        events.append(
            CalendarEvent(
                summary=entry["title"],
                start=event_start,
                end=event_end,
                location=school_name,
                description="\n\n".join(description_parts) or None,
            )
        )

    events.sort(key=lambda event: _event_sort_value(event.start))
    return events


def _exam_entries(
    data: dict[str, Any],
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Return classwork-like journal notes as stable internal items."""
    entries: list[dict[str, Any]] = []
    for source_key in _exam_source_keys(data):
        for item in _iter_values(data.get(source_key)):
            if not isinstance(item, dict):
                continue

            note_date = _note_date(item)
            notes = item.get("notes")
            if note_date is None or not isinstance(notes, list):
                continue

            if note_date < start_date.date() or note_date >= end_date.date():
                continue

            subject = _find_nested_text(
                item,
                ("subject", "subjects", "subjectName", "subject_name"),
            )
            number = _find_value(item, LESSON_NR_KEYS)
            start_time = _parse_time(_find_value(item, START_KEYS))
            end_time = _parse_time(_find_value(item, END_KEYS))
            room = _find_nested_relation_text(item, ROOM_KEYS, _room_text)
            teacher = _find_nested_relation_text(item, TEACHER_KEYS, _teacher_text)
            for note in notes:
                if not isinstance(note, dict) or not _is_exam_note(note):
                    continue

                description = _extract_text(note.get("description"))
                note_type = _note_type_name(note)
                title = _exam_title(subject, note_type, description)
                key = _exam_event_key(
                    note,
                    note_date,
                    title,
                    description,
                )
                entries.append(
                    {
                        "key": key,
                        "title": title,
                        "date": note_date,
                        "number": number,
                        "start_time": start_time,
                        "end_time": end_time,
                        "room": room,
                        "teacher": teacher,
                        "note_type": note_type,
                        "description": description,
                    }
                )

    entries.sort(key=lambda entry: (entry["date"], entry["number"] or 99, entry["title"]))
    return entries


def _exam_source_keys(data: dict[str, Any]) -> tuple[str, ...]:
    """Return journal sources for exams, preferring the compact future range."""
    journal_lessons = data.get("journal_lessons")
    if journal_lessons is not None and not (
        isinstance(journal_lessons, dict) and "error" in journal_lessons
    ):
        return ("journal_lessons",)
    return ("journal_weeks", "journal_lesson_student")


def _is_exam_note(note: dict[str, Any]) -> bool:
    """Return whether a journal note looks like classwork or an exam."""
    note_type = (_note_type_name(note) or "").lower()
    description = (_extract_text(note.get("description")) or "").lower()
    text = f"{note_type} {description}"
    markers = (
        "klassenarbeit",
        "leistungskontrolle",
        " lk",
        "lk ",
        "kurztest",
        "test",
        "arbeit",
        "exam",
        "classwork",
    )
    return note_type == "lk" or any(marker in text for marker in markers)


def _note_type_name(note: dict[str, Any]) -> str | None:
    """Return a readable note type name."""
    note_type = note.get("type")
    if isinstance(note_type, dict):
        return _extract_text(note_type.get("name"))
    return _extract_text(note_type)


def _exam_title(
    subject: str | None,
    note_type: str | None,
    description: str | None,
) -> str:
    """Return a concise exam event title."""
    label = note_type or "Arbeit"
    if subject:
        return f"{label}: {subject}"
    if description:
        first_line = description.splitlines()[0].strip()
        if first_line:
            return first_line[:80]
    return label


def _exam_event_key(
    note: dict[str, Any],
    note_date: date,
    title: str,
    description: str | None,
) -> str:
    """Build a stable duplicate-detection key for exam notes."""
    description_key = " ".join((description or "").split())
    return f"content:{note_date.isoformat()}|{title}|{description_key}"


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
        unique_prefix = coordinator.unique_id_prefix(entry.entry_id)
        self._attr_unique_id = f"{unique_prefix}_timetable"
        self._entry = entry
        self._store = Store(
            coordinator.hass,
            TIMETABLE_HISTORY_STORE_VERSION,
            f"{DOMAIN}_{unique_prefix}_timetable_history",
        )

    async def async_added_to_hass(self) -> None:
        """Load frozen timetable history."""
        await super().async_added_to_hass()
        stored = await self._store.async_load()
        cache: dict[str, CalendarEvent] = {}
        if isinstance(stored, dict):
            for key, value in stored.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                event = _event_from_storage(value)
                if event is not None:
                    cache[key] = event
        self.coordinator.timetable_event_cache = cache

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
        events = _cached_lesson_events(self.coordinator, start_date, end_date)
        await self._async_save_history()
        return events

    async def _async_save_history(self) -> None:
        """Persist frozen timetable history."""
        cutoff = _history_cutoff()
        cache: dict[str, CalendarEvent] = getattr(
            self.coordinator,
            "timetable_event_cache",
            {},
        )
        history = {
            key: _event_to_storage(event)
            for key, event in cache.items()
            if event.start < cutoff
        }
        await self._store.async_save(history)


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
        self._attr_unique_id = f"{coordinator.unique_id_prefix(entry.entry_id)}_absences"
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
        self._attr_unique_id = f"{coordinator.unique_id_prefix(entry.entry_id)}_homework"
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


class BesteSchuleExamCalendar(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], CalendarEntity
):
    """Calendar for visible beste.schule classwork entries."""

    _attr_has_entity_name = True
    _attr_translation_key = "exams"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id_prefix(entry.entry_id)}_exams"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        events = _exam_events(self.coordinator.data, now, now + timedelta(days=90))
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return _exam_events(self.coordinator.data, start_date, end_date)


class BesteSchuleNoticeCalendar(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], CalendarEntity
):
    """Calendar for school-wide beste.schule day notices."""

    _attr_has_entity_name = True
    _attr_translation_key = "notices"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id_prefix(entry.entry_id)}_notices"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        events = _notice_events(self.coordinator.data, now, now + timedelta(days=60))
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return _notice_events(self.coordinator.data, start_date, end_date)
