"""Presence helpers for beste.schule."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .calendar import _absence_events, _cached_lesson_events
from .coordinator import BesteSchuleDataUpdateCoordinator


class LessonBoundaryManager:
    """Schedule one shared lesson-boundary timer for a student coordinator."""

    def __init__(self, coordinator: BesteSchuleDataUpdateCoordinator) -> None:
        self.coordinator = coordinator
        self._listeners: set[Callable[[], None]] = set()
        self._cancel_timer: Callable[[], None] | None = None
        self._remove_coordinator_listener: Callable[[], None] | None = None

    @callback
    def async_register(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity callback and return its unsubscribe function."""
        self._listeners.add(listener)
        if self._remove_coordinator_listener is None:
            self._remove_coordinator_listener = self.coordinator.async_add_listener(
                self._schedule
            )
        self._schedule()

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)
            if self._listeners:
                return
            self._cancel_scheduled_timer()
            if self._remove_coordinator_listener is not None:
                self._remove_coordinator_listener()
                self._remove_coordinator_listener = None

        return remove_listener

    @callback
    def _handle_boundary(self, _now: datetime) -> None:
        """Notify all time-dependent entities at a lesson boundary."""
        self._cancel_timer = None
        for listener in tuple(self._listeners):
            listener()
        self._schedule()

    @callback
    def _schedule(self) -> None:
        """Schedule the next lesson start or end."""
        self._cancel_scheduled_timer()
        if not self._listeners:
            return
        boundary = next_lesson_boundary(self.coordinator)
        if boundary is not None:
            self._cancel_timer = async_track_point_in_time(
                self.coordinator.hass,
                self._handle_boundary,
                boundary,
            )

    @callback
    def _cancel_scheduled_timer(self) -> None:
        """Cancel the active boundary timer."""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None


def lesson_boundary_manager(
    coordinator: BesteSchuleDataUpdateCoordinator,
) -> LessonBoundaryManager:
    """Return the shared boundary manager for a student coordinator."""
    manager = coordinator.lesson_boundary_manager
    if manager is None:
        manager = LessonBoundaryManager(coordinator)
        coordinator.lesson_boundary_manager = manager
    return manager


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


def next_lesson_boundary(
    coordinator: BesteSchuleDataUpdateCoordinator,
) -> datetime | None:
    """Return the next point at which a time-dependent lesson entity changes."""
    now = dt_util.now()
    events = _cached_lesson_events(
        coordinator,
        now - timedelta(minutes=1),
        now + timedelta(days=21),
    )
    boundaries = [
        boundary
        for event in events
        for boundary in (event.start, event.end)
        if boundary > now
    ]
    return min(boundaries, default=None)


def school_day_bounds(
    coordinator: BesteSchuleDataUpdateCoordinator,
) -> tuple[Any | None, Any | None]:
    """Return the first and last timetable event for today."""
    now = dt_util.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    events = _cached_lesson_events(coordinator, today_start, tomorrow_start)
    if not events:
        return None, None
    return min(events, key=lambda event: event.start), max(
        events, key=lambda event: event.end
    )


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
