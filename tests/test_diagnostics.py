"""Tests for downloadable diagnostics."""

from custom_components.beste_schule import diagnostics


def test_timetable_diagnostics_redact_people_but_keep_schedule_fields() -> None:
    """Timetable diagnostics must preserve A/B clues without exposing people."""
    source = {
        "week": "A",
        "subject": {"name": "Englisch"},
        "group": {"name": "5a"},
        "teacher": {"name": "Private Teacher"},
        "students": [{"firstName": "Private", "lastName": "Student"}],
        "lessons": [
            {
                "weekday": 5,
                "nr": 3,
                "teacherName": "Private Teacher",
                "time": {"from": "09:20", "to": "10:05"},
            }
        ],
    }

    redacted = diagnostics._redacted_timetable(source)

    assert redacted["week"] == "A"
    assert redacted["subject"] == {"name": "Englisch"}
    assert redacted["group"] == {"name": "5a"}
    assert redacted["teacher"] != source["teacher"]
    assert redacted["students"] != source["students"]
    assert redacted["lessons"][0]["teacherName"] != "Private Teacher"
    assert redacted["lessons"][0]["weekday"] == 5
    assert redacted["lessons"][0]["nr"] == 3
    assert redacted["lessons"][0]["time"] == {"from": "09:20", "to": "10:05"}
