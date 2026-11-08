"""Privacy-conscious diagnostics for investigating grade notifications."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import coordinators_for_entry

# No tokens, names, comments, student IDs or unfiltered API responses.
SAFE_GRADE_FIELDS = {"value", "grade", "grade_type", "type", "weighting"}
MAX_SAMPLES = 3


def _shape(value: Any, depth: int = 0) -> Any:
    """Describe API structure without exposing personal information."""
    if depth > 5:
        return "<nested>"
    if isinstance(value, dict):
        return {str(k): _shape(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return {"type": "list", "count": len(value),
                "sample": [_shape(v, depth + 1) for v in value[:MAX_SAMPLES]]}
    if value is None:
        return "null"
    return type(value).__name__


def _grade_sample(item: Any) -> Any:
    """Expose keys, types and non-identifying grade values only."""
    if not isinstance(item, dict):
        return _shape(item)
    return {
        "fields": sorted(str(k) for k in item),
        "field_types": {str(k): type(v).__name__ for k, v in item.items()},
        "safe_values": {
            key: item[key] for key in SAFE_GRADE_FIELDS
            if key in item and isinstance(item[key], (str, int, float, bool, type(None)))
            and len(str(item[key])) <= 16
        },
        "collection_shape": _shape(item.get("collection")),
        "subject_shape": _shape(item.get("subject")),
    }


def _grades_diagnostics(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and "error" in response:
        return {"status": "error", "error_type": "api_error"}
    if isinstance(response, dict):
        items = response.get("data")
        result = {
            "response_fields": sorted(str(k) for k in response),
            "pagination_shape": _shape(response.get("meta")),
        }
    else:
        items = response
        result = {"response_type": type(response).__name__}
    if not isinstance(items, list):
        return {**result, "status": "unexpected_shape", "data_shape": _shape(items)}
    return {
        **result,
        "status": "ok",
        "count": len(items),
        "samples": [_grade_sample(item) for item in items[:MAX_SAMPLES]],
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return limited, anonymized API structure for each configured child."""
    coordinators = coordinators_for_entry(hass, entry.entry_id)
    return {
        "integration": DOMAIN,
        "grade_debug_schema": 1,
        "students": [
            {
                "index": index,
                "last_update_success": coordinator.last_update_success,
                "grades": _grades_diagnostics(
                    (coordinator.data or {}).get("grades")
                ),
            }
            for index, coordinator in enumerate(coordinators)
        ],
    }
