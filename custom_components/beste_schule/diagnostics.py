"""Diagnostics support for beste.schule."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_SCHOOL_NAME, CONF_TOKEN, DOMAIN
from .entity import school_name_from_data
from .sensor import (
    _api_average,
    _average,
    _data_list,
    _grade_kind_text,
    _grade_subjects,
    _is_classwork,
    _parse_grade,
    _school_round,
    _subject_grade_values,
    _subject_name,
    _weighted_grade_average,
)

MAX_LIST_ITEMS = 3
MAX_DEPTH = 7
REDACTED_KEYS = {
    CONF_TOKEN,
    "access_token",
    "api_token",
    "bearer",
    "email",
    "mail",
    "phone",
    "telephone",
}
IMPORTANT_KEYS = {
    "date",
    "day",
    "weekday",
    "weekDay",
    "start",
    "startTime",
    "start_time",
    "end",
    "endTime",
    "end_time",
    "from",
    "to",
    "type",
    "status",
    "group",
    "subject",
    "room",
    "rooms",
    "teacher",
    "teachers",
    "times",
    "nr",
    "notes",
    "lessons",
    "data",
    "meta",
    "name",
    "title",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})

    device_info: dict[str, Any] | None = None
    if device is not None:
        device_info = {
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "entry_type": str(device.entry_type),
            "identifiers": sorted(
                f"{identifier[0]}:{identifier[1]}" for identifier in device.identifiers
            ),
        }

    data = coordinator.data or {}
    return {
        "entry": {
            "title": entry.title,
            "data_keys": sorted(entry.data.keys()),
            "stored_school_name": entry.data.get(CONF_SCHOOL_NAME),
        },
        "device_registry": device_info,
        "detected_school_name": school_name_from_data(data),
        "response_summary": {
            key: _summarize_response(value) for key, value in data.items()
        },
        "timetable_samples": {
            key: _sample(value)
            for key, value in data.items()
            if key in {"school", "students"}
            or key.startswith("time_")
            or key.startswith("journal_")
            or key == "substitution_days"
            or key == "grades"
            or key == "finalgrades"
        },
        "grade_debug": _grade_debug(data),
        "homework_debug": _homework_debug(data),
    }


def _grade_debug(data: dict[str, Any]) -> dict[str, Any]:
    """Return compact grade calculation diagnostics grouped by subject."""
    result: dict[str, Any] = {}
    for subject in _grade_subjects(data):
        api_average = _api_average(data, subject)
        classwork_values, other_values = _subject_grade_values(data, subject)
        classwork_average = _average(classwork_values)
        other_average = _average(other_values)
        calculated_average = _weighted_grade_average(classwork_values, other_values)

        result[subject] = {
            "sensor_value": (
                round(api_average, 2)
                if api_average is not None
                else round(calculated_average, 2)
                if calculated_average is not None
                else None
            ),
            "source": "api" if api_average is not None else "calculated",
            "api_average": round(api_average, 2) if api_average is not None else None,
            "calculated_average": (
                round(calculated_average, 2)
                if calculated_average is not None
                else None
            ),
            "rounded_grade": (
                _school_round(calculated_average, classwork_average, other_average)
                if calculated_average is not None
                else None
            ),
            "classwork_values": classwork_values,
            "other_values": other_values,
            "classwork_average": (
                round(classwork_average, 2)
                if classwork_average is not None
                else None
            ),
            "classwork_weight": 2,
            "other_average": (
                round(other_average, 2)
                if other_average is not None
                else None
            ),
            "other_weight": 1,
            "weighting_method": "classwork grades count twice",
            "grade_items": _grade_items_for_subject(data, subject),
            "finalgrade_items": _finalgrade_items_for_subject(data, subject),
        }
    return result


def _grade_items_for_subject(data: dict[str, Any], subject: str) -> list[dict[str, Any]]:
    """Return parseable grade items for one subject without teacher/student details."""
    items: list[dict[str, Any]] = []
    for item in _data_list(data.get("grades")):
        if not isinstance(item, dict) or _subject_name(item) != subject:
            continue

        value = item.get("value")
        parsed = _parse_grade(value)
        if parsed is None:
            continue

        items.append(
            {
                "id": item.get("id"),
                "given_at": item.get("given_at"),
                "value": value,
                "parsed": parsed,
                "kind_text": _grade_kind_text(item) or None,
                "is_classwork": _is_classwork(item),
                "keys": _keys(item),
                "collection": _sample(item.get("collection")),
            }
        )
    return items


def _finalgrade_items_for_subject(data: dict[str, Any], subject: str) -> list[dict[str, Any]]:
    """Return finalgrade fields that may contain API-provided averages."""
    interesting_keys = (
        "id",
        "value",
        "value_int",
        "value_calc",
        "value_calc_int",
        "average",
        "avg",
        "calculation",
        "calculated",
        "calculation_for",
        "calculation_verbal",
        "final_value",
        "interval_id",
        "subject_id",
    )
    items: list[dict[str, Any]] = []
    for item in _data_list(data.get("finalgrades")):
        if not isinstance(item, dict) or _subject_name(item) != subject:
            continue
        items.append(
            {
                key: item.get(key)
                for key in interesting_keys
                if key in item
            }
        )
    return items


def _homework_debug(data: dict[str, Any]) -> dict[str, Any]:
    """Return compact diagnostics for homework calendar source data."""
    note_count = 0
    homework_like_count = 0
    missing_homework_count = 0
    note_type_names: set[str] = set()

    def walk(value: Any) -> None:
        nonlocal note_count, homework_like_count, missing_homework_count
        if isinstance(value, dict):
            if value.get("missing_homework"):
                missing_homework_count += 1
            notes = value.get("notes")
            if isinstance(notes, list):
                note_count += len(notes)
                for note in notes:
                    if not isinstance(note, dict):
                        continue
                    note_type = note.get("type")
                    if isinstance(note_type, dict):
                        name = note_type.get("name")
                        if isinstance(name, str):
                            note_type_names.add(name)
                    text = str(note).lower()
                    if "hausauf" in text or "homework" in text:
                        homework_like_count += 1
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for key in ("journal_lessons", "journal_weeks", "journal_lesson_student"):
        walk(data.get(key))

    return {
        "note_count": note_count,
        "homework_like_note_count": homework_like_count,
        "missing_homework_count": missing_homework_count,
        "note_type_names": sorted(note_type_names),
    }


def _summarize_response(value: Any) -> dict[str, Any]:
    """Return a compact summary for an API response."""
    if isinstance(value, dict) and isinstance(value.get("error"), str):
        return {"type": "error", "error": value["error"]}

    if isinstance(value, list):
        return {
            "type": "list",
            "count": len(value),
            "first_item_keys": _keys(value[0]) if value else [],
        }

    if isinstance(value, dict):
        data = value.get("data")
        summary: dict[str, Any] = {
            "type": "dict",
            "keys": _keys(value),
        }
        if isinstance(data, list):
            summary["data_type"] = "list"
            summary["data_count"] = len(data)
            summary["first_data_item_keys"] = _keys(data[0]) if data else []
        elif isinstance(data, dict):
            summary["data_type"] = "dict"
            summary["data_keys"] = _keys(data)
        return summary

    return {"type": type(value).__name__}


def _keys(value: Any) -> list[str]:
    """Return sorted keys for dict values."""
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    return []


def _sample(value: Any, depth: int = 0) -> Any:
    """Return a small redacted sample that preserves useful structure."""
    if depth >= MAX_DEPTH:
        return f"<{type(value).__name__}>"

    if isinstance(value, dict):
        if isinstance(value.get("error"), str):
            return {"error": value["error"]}

        result: dict[str, Any] = {}
        keys = list(value.keys())
        preferred = [key for key in keys if str(key) in IMPORTANT_KEYS]
        remaining = [key for key in keys if key not in preferred]

        for key in [*preferred, *remaining[:10]]:
            key_str = str(key)
            if key_str in REDACTED_KEYS:
                result[key_str] = "**REDACTED**"
            else:
                result[key_str] = _sample(value[key], depth + 1)
        return result

    if isinstance(value, list):
        return [_sample(item, depth + 1) for item in value[:MAX_LIST_ITEMS]]

    if isinstance(value, str):
        return value[:120]

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return f"<{type(value).__name__}>"
