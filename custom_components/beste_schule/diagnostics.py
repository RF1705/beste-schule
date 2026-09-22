"""Diagnostics support for beste.schule."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .calendar import _coordinator_lesson_events
from .coordinator import coordinators_for_entry

TIMETABLE_REDACT_KEYS = {
    "student",
    "students",
    "selected_student",
    "teacher",
    "teachers",
    "teacherName",
    "teacher_name",
    "forename",
    "firstName",
    "first_name",
    "firstname",
    "lastName",
    "last_name",
    "lastname",
    "email",
    "mail",
    "phone",
    "mobile",
    "birthday",
    "birthdate",
    "address",
}


def _redacted_timetable(value: Any) -> Any:
    """Redact person-related fields while keeping timetable structure intact."""
    if isinstance(value, dict):
        return async_redact_data(value, TIMETABLE_REDACT_KEYS)
    if isinstance(value, list):
        return [
            _redacted_timetable(item) if isinstance(item, (dict, list)) else item
            for item in value
        ]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return focused timetable diagnostics for a config entry."""
    children: list[dict[str, Any]] = []

    for index, coordinator in enumerate(
        coordinators_for_entry(hass, entry.entry_id),
        start=1,
    ):
        events = _coordinator_lesson_events(coordinator, include_cancelled=True)
        cache_start = getattr(coordinator, "timetable_cache_start", None)
        children.append(
            {
                "child": index,
                "data_revision": coordinator.data_revision,
                "timetable_cache_start": (
                    cache_start.isoformat()
                    if hasattr(cache_start, "isoformat")
                    else None
                ),
                "time_tables_current": _redacted_timetable(
                    coordinator.data.get("time_tables_current")
                ),
                "generated_lessons": [
                    {
                        "summary": event.summary,
                        "start": event.start.isoformat(),
                        "end": event.end.isoformat(),
                    }
                    for event in events
                ],
            }
        )

    return {
        "generated_at": dt_util.now().isoformat(),
        "config_entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "options": dict(entry.options),
        },
        "children": children,
    }
