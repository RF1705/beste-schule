"""To-do support for beste.schule."""

from __future__ import annotations

from datetime import timedelta
import hashlib

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
        self._store = Store(
            coordinator.hass,
            STORE_VERSION,
            f"{DOMAIN}_{unique_prefix}_homework_todo_completed",
        )

    async def async_added_to_hass(self) -> None:
        """Load locally completed homework items."""
        await super().async_added_to_hass()
        stored = await self._store.async_load()
        if isinstance(stored, list):
            self._completed_uids = {uid for uid in stored if isinstance(uid, str)}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return homework as to-do items."""
        now = dt_util.now()
        entries = _homework_entries(
            self.coordinator.data,
            now - timedelta(days=30),
            now + timedelta(days=90),
        )
        items: list[TodoItem] = []
        active_uids: set[str] = set()
        for entry in entries:
            uid = _uid_from_key(entry["key"])
            active_uids.add(uid)
            items.append(
                TodoItem(
                    uid=uid,
                    summary=entry["title"],
                    status=COMPLETE if uid in self._completed_uids else NEEDS_ACTION,
                    due=entry["date"],
                    description=entry["description"],
                )
            )
        self._completed_uids.intersection_update(active_uids)
        return items

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


def _uid_from_key(key: str) -> str:
    """Return a stable Home Assistant to-do uid."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"besteschule_{digest}"
