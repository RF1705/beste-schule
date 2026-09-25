"""Tests for timetable generation caching."""

from datetime import datetime, time, timedelta
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


def test_period_time_map_uses_timetable_lesson_time_relation() -> None:
    """The timetable include must provide period numbers and their new time relation."""
    data = {
        "time_tables_current": {
            "data": {
                "lessons": [
                    {
                        "nr": 3,
                        "time": {"from": "09:50", "to": "10:35"},
                    }
                ]
            }
        }
    }

    assert calendar._period_time_map(data) == {3: (time(9, 50), time(10, 35))}


def test_lesson_events_respect_timetable_week_types() -> None:
    """Recurring lessons should only be generated in their configured A/B week."""
    tz = ZoneInfo("Europe/Berlin")
    data = {
        "time_tables_current": {
            "data": {
                "valid_from": "2026-08-17",
                "valid_to": "2026-09-30",
                "weeks": [
                    {"nr": 34, "year": "2026", "types": ["A"]},
                    {"nr": 35, "year": "2026", "types": ["B"]},
                ],
                "lessons": [
                    {
                        "weeks": ["A"],
                        "weekday": 1,
                        "nr": 1,
                        "subject": {"name": "Musik"},
                        "time": {"from": "07:30", "to": "08:15"},
                    },
                    {
                        "weeks": ["B"],
                        "weekday": 1,
                        "nr": 1,
                        "subject": {"name": "Biologie"},
                        "time": {"from": "07:30", "to": "08:15"},
                    },
                ],
            }
        }
    }

    events = calendar._lesson_events(
        data,
        datetime(2026, 8, 17, tzinfo=tz),
        datetime(2026, 8, 31, tzinfo=tz),
    )

    assert [(event.start.date(), event.summary) for event in events] == [
        (datetime(2026, 8, 17).date(), "Musik"),
        (datetime(2026, 8, 24).date(), "Biologie"),
    ]


def test_lesson_events_keep_untyped_lessons() -> None:
    """Lessons without a week restriction should remain valid in every week."""
    tz = ZoneInfo("Europe/Berlin")
    data = {
        "time_tables_current": {
            "data": {
                "valid_from": "2026-08-17",
                "valid_to": "2026-09-30",
                "weeks": [
                    {"nr": 34, "year": "2026", "types": ["A"]},
                    {"nr": 35, "year": "2026", "types": ["B"]},
                ],
                "lessons": [
                    {
                        "weekday": 1,
                        "nr": 1,
                        "subject": {"name": "Mathematik"},
                        "time": {"from": "07:30", "to": "08:15"},
                    }
                ],
            }
        }
    }

    events = calendar._lesson_events(
        data,
        datetime(2026, 8, 17, tzinfo=tz),
        datetime(2026, 8, 31, tzinfo=tz),
    )

    assert [(event.start.date(), event.summary) for event in events] == [
        (datetime(2026, 8, 17).date(), "Mathematik"),
        (datetime(2026, 8, 24).date(), "Mathematik"),
    ]
