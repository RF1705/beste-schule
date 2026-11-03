"""Regression tests for journal note classification."""

import pytest

from custom_components.beste_schule.calendar import _is_exam_note, _is_homework_note


@pytest.mark.parametrize("note_type", ["WÜ", "TÜ", "WUE", "TUE", "KA", "LK"])
def test_exam_abbreviations_are_recognized(note_type: str) -> None:
    assert _is_exam_note({"type": note_type, "description": "Mathematik"})


@pytest.mark.parametrize(
    "description",
    ["Wissensüberprüfung", "Wissensueberpruefung", "tägliche Übung", "taegliche Uebung"],
)
def test_exam_full_names_are_recognized(description: str) -> None:
    assert _is_exam_note({"type": "Sonstiges", "description": description})


def test_homework_with_exam_mention_is_not_exam() -> None:
    note = {"type": "HA", "description": "Lernen für die Klassenarbeit"}
    assert _is_homework_note(note)
    assert not _is_exam_note(note)


def test_exam_abbreviation_is_not_matched_inside_other_words() -> None:
    assert not _is_exam_note({"type": "Sonstiges", "description": "Tür öffnen"})
