"""Tests for shared lesson-boundary scheduling."""

from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.beste_schule import presence


def test_entities_share_one_boundary_manager(monkeypatch) -> None:
    """All time-dependent entities should use one coordinator listener and timer."""
    remove_coordinator_listener = Mock()
    add_coordinator_listener = Mock(return_value=remove_coordinator_listener)
    coordinator = SimpleNamespace(
        lesson_boundary_manager=None,
        async_add_listener=add_coordinator_listener,
    )
    monkeypatch.setattr(presence, "next_lesson_boundary", lambda _coordinator: None)

    manager = presence.lesson_boundary_manager(coordinator)
    assert presence.lesson_boundary_manager(coordinator) is manager

    remove_first = manager.async_register(Mock())
    remove_second = manager.async_register(Mock())
    assert add_coordinator_listener.call_count == 1

    remove_first()
    remove_coordinator_listener.assert_not_called()
    remove_second()
    remove_coordinator_listener.assert_called_once_with()
