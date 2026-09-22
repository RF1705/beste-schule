"""Tests for timetable generation caching."""

from datetime import datetime, time, timedelta

import logging
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


@pytest.mark.parametrize(
    "label",
    [
        "WÜ",
        "TÜ",
        "WÜ/TÜ",
        "wü: Brüche",
        "TÜ – Vokabeln",
        "WUE",
        "TUE",
        "Wissensüberprüfung",
        "Wissensüberprüfungen",
        "Wissensueberpruefung",
        "Tägliche Übung",
        "Taegliche Uebung",
        "LK",
        "Klassenarbeit",
        "Kurztest",
    ],
)
@pytest.mark.parametrize("field", ["type", "description"])
def test_exam_recognition(label, field) -> None:
    """Recognize school labels in both supported note fields."""
    note = {field: {"name": label} if field == "type" else label}
    assert calendar._is_exam_note(note)


@pytest.mark.parametrize(
    "label", ["Türdienst", "Wünsche", "Tuebingen", "Wuesten", "Hausaufgaben"]
)
def test_exam_abbreviations_require_whole_words(label) -> None:
    """Short labels must not match within unrelated words."""
    assert not calendar._is_exam_note({"description": label})


def test_wue_note_creates_one_calendar_event() -> None:
    """Recognized notes become events, with duplicate API notes collapsed."""
    start = datetime(2026, 9, 22, tzinfo=ZoneInfo("Europe/Berlin"))
    lesson = {
        "date": "2026-09-23",
        "subject": "Mathematik",
        "notes": [{"id": 1, "type": {"name": "WÜ"}, "description": "Brüche"}],
    }
    events = calendar._exam_events(
        {"journal_lessons": {"data": [lesson, lesson]}},
        start,
        start + timedelta(days=7),
    )
    assert len(events) == 1
    assert "WÜ" in events[0].summary
    assert events[0].start.isoformat() == "2026-09-23"


def test_exam_debug_explains_rejections_without_personal_data(caplog) -> None:
    """Diagnose alternate sources and rejected notes without dumping API data."""
    start = datetime(2026, 9, 22, tzinfo=ZoneInfo("Europe/Berlin"))
    note = {
        "type": {"name": "WÜ"},
        "description": "Secret pupil and topic",
        "id": 987654321,
    }
    data = {
        "journal_lessons": {
            "data": [
                {"date": "2026-09-23", "notes": [note, {"type": "Private type name"}]},
                {"notes": [note]},
                {"date": "2026-10-23", "notes": [note]},
                {"notes": {"data": [note]}},
            ]
        },
        "journal_weeks": {"data": [{"date": "2026-09-23", "notes": [note]}]},
        "journal_lesson_student": {"error": "Secret API error"},
        "token": "Secret token",
    }
    with caplog.at_level(logging.DEBUG, logger=calendar.__name__):
        entries = calendar._exam_entries(data, start, start + timedelta(days=7))
    assert len(entries) == 1
    for reason in (
        "unrecognized",
        "missing_date",
        "outside_requested_range",
        "source_not_selected",
        "accepted_before_deduplication",
        "unsupported_notes_shape",
    ):
        assert reason in caplog.text
    assert "status=error" in caplog.text
    assert "'wü':" in caplog.text
    for secret in ("Secret", "Private type name", "987654321"):
        assert secret not in caplog.text


def test_exam_diagnostics_are_disabled_without_debug(monkeypatch) -> None:
    """Normal calendar requests do not scan extra sources for diagnostics."""
    start = datetime(2026, 9, 22, tzinfo=ZoneInfo("Europe/Berlin"))
    diagnostic = Mock()
    monkeypatch.setattr(calendar, "_log_exam_diagnostics", diagnostic)
    monkeypatch.setattr(calendar.LOGGER, "isEnabledFor", lambda level: False)
    calendar._exam_entries({}, start, start + timedelta(days=7))
    diagnostic.assert_not_called()
