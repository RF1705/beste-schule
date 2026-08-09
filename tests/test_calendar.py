"""Tests for timetable generation caching."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEvent
import pytest

from custom_components.beste_schule import calendar


def test_generated_timetable_is_cached_per_data_revision(monkeypatch) -> None:
    """Multiple entities should share one timetable calculation per refresh."""
    now = datetime(2026, 7, 19, 12, tzinfo=ZoneInfo("Europe/Berlin"))
    event = CalendarEvent(
        summary="Mathematik",
        start=now + timedelta(days=1),
        end=now + timedelta(days=1, minutes=45),
    )
    generate = Mock(return_value=[event])
    coordinator = SimpleNamespace(
        data={},
        data_revision=1,
        timetable_generated_cache={},
    )
    monkeypatch.setattr(calendar.dt_util, "now", lambda: now)
    monkeypatch.setattr(calendar, "_lesson_events", generate)

    assert calendar._coordinator_lesson_events(coordinator) == [event]
    assert calendar._coordinator_lesson_events(coordinator) == [event]
    assert generate.call_count == 1

    coordinator.data_revision = 2
    assert calendar._coordinator_lesson_events(coordinator) == [event]
    assert generate.call_count == 2


@pytest.mark.asyncio
async def test_history_save_checks_for_changes_during_write() -> None:
    """A snapshot created during storage I/O must trigger a follow-up save."""
    entity = object.__new__(calendar.BesteSchuleTimetableCalendar)
    entity._history_save_pending = True
    entity._async_save_history = AsyncMock()
    entity._schedule_history_save = Mock()

    await entity._async_save_scheduled_history()

    assert entity._history_save_pending is False
    entity._schedule_history_save.assert_called_once_with()
