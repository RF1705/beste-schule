"""The beste.schule integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import BesteSchuleApi
from .const import CONF_SCHOOL_NAME, CONF_TOKEN, DEFAULT_API_URL, DOMAIN, PLATFORMS
from .coordinator import BesteSchuleDataUpdateCoordinator
from .entity import school_name_from_data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up beste.schule from a config entry."""
    api = BesteSchuleApi(
        hass,
        DEFAULT_API_URL,
        entry.data[CONF_TOKEN],
    )
    coordinator = BesteSchuleDataUpdateCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
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
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    if device is None:
        return

    device_registry.async_update_device(
        device.id,
        manufacturer="beste.schule",
        model=school_name,
    )
