"""Sensors for beste.schule."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BesteSchuleDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up beste.schule sensors."""
    coordinator: BesteSchuleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BesteSchuleCountSensor(entry, coordinator, "Announcements", "announcements"),
            BesteSchuleCountSensor(entry, coordinator, "Checklists", "checklists"),
            BesteSchuleCountSensor(entry, coordinator, "Grades", "grades"),
            BesteSchuleCountSensor(entry, coordinator, "Final grades", "finalgrades"),
        ]
    )


class BesteSchuleCountSensor(
    CoordinatorEntity[BesteSchuleDataUpdateCoordinator], SensorEntity
):
    """Count items returned by a beste.schule route."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BesteSchuleDataUpdateCoordinator,
        name: str,
        data_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = data_key
        self._attr_unique_id = f"{entry.entry_id}_{data_key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="beste.schule",
            name=entry.title,
            configuration_url="https://beste.schule",
        )
        self._data_key = data_key

    @property
    def native_value(self) -> int | None:
        """Return the number of returned items, if available."""
        value = self.coordinator.data.get(self._data_key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict) and isinstance(value.get("data"), list):
            return len(value["data"])
        return None
