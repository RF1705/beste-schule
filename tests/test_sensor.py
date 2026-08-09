"""Tests for safe grade formula evaluation."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from custom_components.beste_schule import sensor
from custom_components.beste_schule.sensor import (
    _evaluate_formula,
    _grade_year_history,
    _timetable_card_rows,
)


def test_evaluate_formula_uses_case_insensitive_variables() -> None:
    """API formula variables should work regardless of their casing."""
    assert _evaluate_formula("So_sum / So_count", {"so_sum": 7, "so_count": 2}) == 3.5


def test_evaluate_formula_rejects_calls() -> None:
    """API formulas must not execute arbitrary Python calls."""
    with pytest.raises(ValueError, match="Unsupported calculation rule"):
        _evaluate_formula("abs(-1)", {})


def test_empty_timetable_card_result_is_cached(monkeypatch) -> None:
    """An empty week must not regenerate its timetable on every state read."""
    now = datetime(2026, 7, 19, 12, tzinfo=ZoneInfo("Europe/Berlin"))
    coordinator = SimpleNamespace(
        data_revision=3,
        timetable_card_cache={(3, now.date(), 0): []},
    )
    generate = Mock(side_effect=AssertionError("cache miss"))
    monkeypatch.setattr(sensor.dt_util, "now", lambda: now)
    monkeypatch.setattr(sensor, "_coordinator_lesson_events", generate)

    assert _timetable_card_rows(coordinator, 0) == []
    generate.assert_not_called()


def test_grade_history_uses_fresh_value_for_current_year(monkeypatch) -> None:
    """The cached history must not make the current school year look stale."""
    now = datetime(2026, 8, 9, 12, tzinfo=ZoneInfo("Europe/Berlin"))
    monkeypatch.setattr(sensor.dt_util, "now", lambda: now)
    data = {
        "years": {
            "data": [
                {
                    "id": 7,
                    "name": "Schuljahr 2026/27",
                    "from": "2026-08-01",
                    "to": "2027-07-31",
                }
            ]
        },
        "finalgrades": {"data": [{"subject": "Mathematik", "value_calc": 2.0}]},
        "grade_years": {
            "7": {
                "year": {"id": 7, "name": "Schuljahr 2026/27"},
                "finalgrades": {"data": [{"subject": "Mathematik", "value_calc": 3.0}]},
            }
        },
    }

    assert _grade_year_history(data, "Mathematik") == {"2026/27": 2.0}
