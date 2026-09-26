"""Number entities for beste.schule."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import BesteSchuleDataUpdateCoordinator, coordinators_for_entry
from .entity import besteschule_device_info

MIN_WEEK_OFFSET = 0
MAX_WEEK_OFFSET = 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule number entities."""
    async_add_entities(
        [
            BesteSchuleTimetableWeekOffsetNumber(entry, coordinator)
            for coordinator in coordinators_for_entry(hass, entry.entry_id)
        ]
    )


def _default_week_offset() -> int:
    """Show the upcoming week by default on weekends."""
    return 1 if dt_util.now().weekday() >= 5 else 0


class BesteSchuleTimetableWeekOffsetNumber(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator],
    NumberEntity,
):
    """Select the timetable week exposed to compatible dashboard cards."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-arrow-right"
    _attr_translation_key = "timetable_week_offset"
    _attr_native_min_value = MIN_WEEK_OFFSET
    _attr_native_max_value = MAX_WEEK_OFFSET
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = (
            f"{coordinator.unique_id_prefix(entry.entry_id)}"
            "_timetable_week_offset"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return besteschule_device_info(self._entry, self.coordinator.data)

    @property
    def native_value(self) -> float:
        """Return the selected week offset."""
        selected = self.coordinator.timetable_card_week_offset
        return float(_default_week_offset() if selected is None else selected)

    async def async_set_native_value(self, value: float) -> None:
        """Select another timetable week and notify dependent entities."""
        week_offset = max(
            MIN_WEEK_OFFSET,
            min(MAX_WEEK_OFFSET, int(round(value))),
        )
        self.coordinator.timetable_card_week_offset = week_offset
        self.coordinator.timetable_card_cache.clear()
        self.coordinator.async_update_listeners()

    async def async_added_to_hass(self) -> None:
        """Refresh the timetable sensor after this entity is registered."""
        await super().async_added_to_hass()
        self.coordinator.async_update_listeners()
