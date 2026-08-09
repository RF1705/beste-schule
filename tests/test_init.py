"""Tests for config-entry migration helpers."""

from copy import deepcopy

import pytest

from custom_components import beste_schule


@pytest.mark.asyncio
async def test_single_student_storage_is_migrated_without_overwrite(
    monkeypatch,
) -> None:
    """Legacy state should follow new IDs while existing new state wins."""
    values = {
        "beste_schule_entry_timetable_history": {"lesson": "old"},
        "beste_schule_entry_homework_todo_completed": ["done"],
        "beste_schule_entry_homework_todo_history": {"task": "old"},
        "beste_schule_entry_42_homework_todo_history": {"task": "new"},
    }

    class FakeStore:
        def __init__(self, _hass, _version, key) -> None:
            self.key = key

        async def async_load(self):
            return deepcopy(values.get(self.key))

        async def async_save(self, value) -> None:
            values[self.key] = deepcopy(value)

    monkeypatch.setattr(beste_schule, "Store", FakeStore)

    await beste_schule._async_migrate_legacy_storage(
        None,
        "entry",
        "42",
    )

    assert values["beste_schule_entry_42_timetable_history"] == {"lesson": "old"}
    assert values["beste_schule_entry_42_homework_todo_completed"] == ["done"]
    assert values["beste_schule_entry_42_homework_todo_history"] == {"task": "new"}
