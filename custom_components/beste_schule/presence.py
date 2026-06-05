"""Presence helpers for beste.schule."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .calendar import _absence_events, _lesson_events


def current_lesson(data: dict[str, Any]) -> Any | None:
    """Return the current timetable event, if any."""
    now = dt_util.now()
    return next(
        (
            event
            for event in _lesson_events(
                data,
                now - timedelta(minutes=1),
                now + timedelta(minutes=1),
            )
            if event.start <= now < event.end
        ),
        None,
    )


def is_at_school(data: dict[str, Any]) -> bool:
    """Return whether the student is currently in school."""
    now = dt_util.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    if _absence_events(data, today_start, tomorrow_start):
        return False

    return current_lesson(data) is not None
