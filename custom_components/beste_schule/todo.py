"""To-do support for beste.schule."""

from __future__ import annotations

from datetime import date
from datetime import timedelta
import hashlib
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .calendar import _homework_entries
from .const import (
    CONF_ENABLE_HOMEWORK_TODO,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .coordinator import BesteSchuleDataUpdateCoordinator, coordinators_for_entry
from .entity import besteschule_device_info

STORE_VERSION = 1
HISTORY_STORE_VERSION = 1
HISTORY_RETENTION_DAYS = 365
NEEDS_ACTION = TodoItemStatus.NEEDS_ACTION
COMPLETE = (
    TodoItemStatus.COMPLETE
    if hasattr(TodoItemStatus, "COMPLETE")
    else TodoItemStatus.COMPLETED
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule to-do lists."""
    options = {**DEFAULT_OPTIONS, **entry.options}
    if not options[CONF_ENABLE_HOMEWORK_TODO]:
        async_add_entities([])
        return

    async_add_entities(
        [
            BesteSchuleHomeworkTodoList(entry, coordinator)
            for coordinator in coordinators_for_entry(hass, entry.entry_id)
        ]
    )


class BesteSchuleHomeworkTodoList(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], TodoListEntity
):
    """To-do list for visible beste.schule homework entries."""

    _attr_has_entity_name = True
    _attr_translation_key = "homework"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        unique_prefix = coordinator.unique_id_prefix(entry.entry_id)
        self._attr_unique_id = f"{unique_prefix}_homework_todo"
        self._completed_uids: set[str] = set()
        self._history: dict[str, dict[str, Any]] = {}
        self._history_save_pending = False
        self._store = Store(
            coordinator.hass,
            STORE_VERSION,
            f"{DOMAIN}_{unique_prefix}_homework_todo_completed",
        )
        self._history_store = Store(
            coordinator.hass,
            HISTORY_STORE_VERSION,
            f"{DOMAIN}_{unique_prefix}_homework_todo_history",
        )

    async def async_added_to_hass(self) -> None:
        """Load locally completed and cached homework items."""
        await super().async_added_to_hass()
        stored = await self._store.async_load()
        if isinstance(stored, list):
            self._completed_uids = {uid for uid in stored if isinstance(uid, str)}
        stored_history = await self._history_store.async_load()
        if isinstance(stored_history, dict):
            history: dict[str, dict[str, Any]] = {}
            for uid, item in stored_history.items():
                stored_entry = _stored_entry(item)
                if isinstance(uid, str) and stored_entry is not None:
                    history[uid] = stored_entry
            self._history = history
        if self._merge_current_entries():
            await self._async_save_history()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return homework as to-do items."""
        if self._merge_current_entries():
            self._schedule_history_save()
        active_uids = set(self._history)
        self._completed_uids.intersection_update(active_uids)
        return [
            TodoItem(
                uid=uid,
                summary=entry["title"],
                status=COMPLETE if uid in self._completed_uids else NEEDS_ACTION,
                due=entry["date"],
                description=entry["description"],
            )
            for uid, entry in sorted(
                self._history.items(),
                key=lambda item: (item[1]["date"], item[1]["title"]),
            )
        ]

    def _merge_current_entries(self) -> bool:
        """Merge currently visible API homework into the local history."""
        now = dt_util.now()
        entries = _homework_entries(
            self.coordinator.data,
            now - timedelta(days=30),
            now + timedelta(days=90),
        )
        changed = False
        for entry in entries:
            uid = _uid_from_key(entry["key"])
            history_entry = _entry_to_history(entry)
            if self._history.get(uid) != history_entry:
                self._history[uid] = history_entry
                changed = True
        retention_date = now.date() - timedelta(days=HISTORY_RETENTION_DAYS)
        expired_uids = {
            uid
            for uid, entry in self._history.items()
            if isinstance(entry.get("date"), date) and entry["date"] < retention_date
        }
        if expired_uids:
            for uid in expired_uids:
                self._history.pop(uid, None)
            self._completed_uids.difference_update(expired_uids)
            changed = True
        return changed

    def _handle_coordinator_update(self) -> None:
        """Merge fresh API data before Home Assistant reads the to-do state."""
        if self._merge_current_entries():
            self._schedule_history_save()
        super()._handle_coordinator_update()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Store the local done state for a homework item."""
        if item.uid is None:
            return

        if item.status == COMPLETE:
            self._completed_uids.add(item.uid)
        else:
            self._completed_uids.discard(item.uid)

        await self._store.async_save(sorted(self._completed_uids))
        self.async_write_ha_state()

    def _schedule_history_save(self) -> None:
        """Schedule a history save without awaiting from sync properties."""
        if self._history_save_pending:
            return
        self._history_save_pending = True
        self.hass.async_create_task(self._async_save_history())

    async def _async_save_history(self) -> None:
        """Persist locally cached homework items."""
        self._history_save_pending = False
        await self._history_store.async_save(
            {uid: _entry_to_storage(entry) for uid, entry in self._history.items()}
        )


def _uid_from_key(key: str) -> str:
    """Return a stable Home Assistant to-do uid."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"besteschule_{digest}"


def _entry_to_storage(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-storable homework entry."""
    entry_date = entry.get("date")
    return {
        "key": entry.get("key"),
        "title": entry.get("title"),
        "date": entry_date.isoformat() if isinstance(entry_date, date) else entry_date,
        "description": entry.get("description"),
    }


def _entry_to_history(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized in-memory homework entry."""
    entry_date = entry.get("date")
    if isinstance(entry_date, str):
        try:
            entry_date = date.fromisoformat(entry_date)
        except ValueError:
            pass
    return {
        "key": entry.get("key"),
        "title": entry.get("title"),
        "date": entry_date,
        "description": entry.get("description"),
    }


def _stored_entry(value: Any) -> dict[str, Any] | None:
    """Return a normalized stored homework entry."""
    if not isinstance(value, dict):
        return None

    title = value.get("title")
    entry_date = value.get("date")
    if not isinstance(title, str) or not isinstance(entry_date, str):
        return None

    try:
        parsed_date = date.fromisoformat(entry_date)
    except ValueError:
        return None

    return {
        "key": value.get("key"),
        "title": title,
        "date": parsed_date,
        "description": value.get("description"),
    }
