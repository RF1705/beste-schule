"""Presence helpers for beste.schule."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .calendar import _absence_events, _cached_lesson_events, _lesson_events
from .coordinator import BesteSchuleDataUpdateCoordinator


def current_lesson(coordinator: BesteSchuleDataUpdateCoordinator) -> Any | None:
    """Return the current timetable event, if any."""
    now = dt_util.now()
    return next(
        (
            event
            for event in _cached_lesson_events(
                coordinator,
                now - timedelta(minutes=1),
                now + timedelta(minutes=1),
            )
            if event.start <= now < event.end
        ),
        None,
    )


def school_day_bounds(
    coordinator: BesteSchuleDataUpdateCoordinator,
) -> tuple[Any | None, Any | None]:
    """Return the first and last timetable event for today."""
    now = dt_util.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    events = _lesson_events(coordinator.data, today_start, tomorrow_start)
    if not events:
        return None, None
    return min(events, key=lambda event: event.start), max(events, key=lambda event: event.end)


def is_at_school(coordinator: BesteSchuleDataUpdateCoordinator) -> bool:
    """Return whether the student is currently in school."""
    now = dt_util.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    if _absence_events(coordinator.data, today_start, tomorrow_start):
        return False

    first_lesson, last_lesson = school_day_bounds(coordinator)
    if first_lesson is None or last_lesson is None:
        return False
    return first_lesson.start <= now < last_lesson.end
