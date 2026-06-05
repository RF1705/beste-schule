"""Diagnostics support for beste.schule."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_SCHOOL_NAME, CONF_TOKEN, DOMAIN
from .entity import school_name_from_data

MAX_LIST_ITEMS = 3
MAX_DEPTH = 5
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
    "subject",
    "room",
    "teacher",
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
            if key.startswith("time_") or key.startswith("journal_")
        },
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
