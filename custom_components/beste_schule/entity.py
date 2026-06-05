"""Shared entity helpers for beste.schule."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def _text(value: Any) -> str | None:
    """Return a stripped string value."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _name_from_dict(value: dict[str, Any]) -> str | None:
    """Extract a readable name from a dict."""
    for key in (
        "name",
        "displayName",
        "display_name",
        "fullName",
        "full_name",
        "title",
    ):
        text = _text(value.get(key))
        if text:
            return text
    return None


def _school_name_from_data(data: Any) -> str | None:
    """Find a school name in common beste.schule response shapes."""
    if isinstance(data, list):
        for item in data:
            name = _school_name_from_data(item)
            if name:
                return name
        return None

    if not isinstance(data, dict):
        return None

    for key in ("school", "currentSchool", "current_school"):
        value = data.get(key)
        if isinstance(value, dict):
            name = _name_from_dict(value)
            if name:
                return name
        name = _text(value)
        if name:
            return name

    for key in ("me", "user", "profile", "student", "child", "data"):
        name = _school_name_from_data(data.get(key))
        if name:
            return name

    return None


def besteschule_device_info(entry: ConfigEntry, data: dict[str, Any]) -> DeviceInfo:
    """Return Home Assistant device info for beste.schule entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=_school_name_from_data(data) or "beste.schule",
        model="beste.schule",
        name=entry.title,
        configuration_url="https://beste.schule",
    )
