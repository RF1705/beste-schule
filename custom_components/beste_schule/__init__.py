"""The beste.schule integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import BesteSchuleApi, BesteSchuleApiError, BesteSchuleAuthError
from .const import (
    CONF_MIGRATE_STUDENT_IDS,
    CONF_SCHOOL_NAME,
    CONF_TOKEN,
    DEFAULT_API_URL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import school_name_from_data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up beste.schule from a config entry."""
    api = BesteSchuleApi(
        hass,
        DEFAULT_API_URL,
        entry.data[CONF_TOKEN],
    )
    students = await _fetch_students(api)
    student_items = _student_items(students)
    if not student_items:
        student_items = [None]

    coordinators: list[BesteSchuleDataUpdateCoordinator] = []
    for student in student_items:
        coordinator = BesteSchuleDataUpdateCoordinator(hass, api, student, students)
        coordinator.timetable_cache_start = _entry_start_of_day(entry) or _start_of_day(
            dt_util.now()
        )
        await coordinator.async_config_entry_first_refresh()
        coordinators.append(coordinator)

    if entry.data.get(CONF_MIGRATE_STUDENT_IDS):
        await _async_migrate_student_identifiers(
            hass,
            entry,
            [coordinator.student_id for coordinator in coordinators],
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    for coordinator in coordinators:
        _async_update_device_info(hass, entry, coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _async_update_device_info(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: BesteSchuleDataUpdateCoordinator,
) -> None:
    """Update existing device registry data after the first API refresh."""
    school_name = school_name_from_data(coordinator.data)
    if not school_name:
        return

    if entry.data.get(CONF_SCHOOL_NAME) != school_name:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_SCHOOL_NAME: school_name},
        )

    device_registry = dr.async_get(hass)
    student_id = coordinator.student_id
    identifier = f"{entry.entry_id}:{student_id}"
    device = device_registry.async_get_device(identifiers={(DOMAIN, identifier)})
    if device is None:
        return

    device_registry.async_update_device(
        device.id,
        manufacturer="beste.schule",
        model=school_name,
    )


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload beste.schule when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Mark version-one registry identifiers for a safe setup-time migration."""
    if entry.version < 2:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_MIGRATE_STUDENT_IDS: True},
            version=2,
        )
    return True


async def _async_migrate_student_identifiers(
    hass: HomeAssistant,
    entry: ConfigEntry,
    student_ids: list[str],
) -> None:
    """Migrate legacy single-child storage, entity, and device identifiers."""
    if student_ids:
        await _async_migrate_legacy_storage(
            hass,
            entry.entry_id,
            student_ids[0],
        )

    entity_registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    )
    if student_ids:
        student_id = student_ids[0]
        old_prefix = f"{entry.entry_id}_"
        new_prefix = f"{entry.entry_id}_{student_id}_"
        scoped_prefixes = tuple(f"{entry.entry_id}_{value}_" for value in student_ids)
        for item in registry_entries:
            if item.unique_id.startswith(old_prefix) and not item.unique_id.startswith(
                scoped_prefixes
            ):
                entity_registry.async_update_entity(
                    item.entity_id,
                    new_unique_id=(
                        f"{new_prefix}{item.unique_id.removeprefix(old_prefix)}"
                    ),
                )

        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.entry_id)}
        )
        if device is not None:
            device_registry.async_update_device(
                device.id,
                new_identifiers={(DOMAIN, f"{entry.entry_id}:{student_id}")},
            )

    updated_data = dict(entry.data)
    updated_data.pop(CONF_MIGRATE_STUDENT_IDS, None)
    hass.config_entries.async_update_entry(entry, data=updated_data)


async def _async_migrate_legacy_storage(
    hass: HomeAssistant,
    entry_id: str,
    student_id: str,
) -> None:
    """Copy legacy local state to the new student-scoped storage keys."""
    for suffix in (
        "timetable_history",
        "homework_todo_completed",
        "homework_todo_history",
    ):
        old_store = Store(hass, 1, f"{DOMAIN}_{entry_id}_{suffix}")
        new_store = Store(hass, 1, f"{DOMAIN}_{entry_id}_{student_id}_{suffix}")
        if await new_store.async_load() is not None:
            continue
        old_data = await old_store.async_load()
        if old_data is not None:
            await new_store.async_save(old_data)


def _entry_start_of_day(entry: ConfigEntry):
    """Return the config entry creation date at local midnight."""
    created_at = getattr(entry, "created_at", None)
    if created_at is None:
        return None
    return _start_of_day(dt_util.as_local(created_at))


def _start_of_day(value):
    """Return a datetime at the beginning of the given local day."""
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


async def _fetch_students(api: BesteSchuleApi) -> Any:
    """Fetch the students list, falling back to single-child mode on API errors."""
    try:
        return await api.fetch_students()
    except BesteSchuleAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except BesteSchuleApiError:
        return None


def _student_items(students: Any) -> list[dict[str, Any]]:
    """Return all student dictionaries from a students API response."""
    if isinstance(students, dict):
        data = students.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
    if isinstance(students, list):
        return [item for item in students if isinstance(item, dict)]
    return []
