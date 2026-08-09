"""Shared entity helpers for beste.schule."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_SCHOOL_NAME, DOMAIN

KNOWN_SCHOOL_COORDINATES = {
    1008: (51.091054, 13.711921),
}


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


def school_name_from_data(data: Any) -> str | None:
    """Find a school name in common beste.schule response shapes."""
    if isinstance(data, list):
        for item in data:
            name = school_name_from_data(item)
            if name:
                return name
        return None

    if not isinstance(data, dict):
        return None

    name = _name_from_dict(data)
    if name:
        return name

    for key in ("school", "currentSchool", "current_school"):
        value = data.get(key)
        if isinstance(value, dict):
            name = _name_from_dict(value)
            if name:
                return name
            name = school_name_from_data(value)
            if name:
                return name
        name = _text(value)
        if name:
            return name

    for key in ("me", "user", "profile", "student", "child", "data"):
        name = school_name_from_data(data.get(key))
        if name:
            return name

    return None


def school_address_from_data(data: Any) -> str | None:
    """Find a school address in common beste.schule response shapes."""
    school = _school_data(data)
    if not isinstance(school, dict):
        return None

    street = _text(school.get("street"))
    street_nr = _text(school.get("street_nr"))
    postal_code = _text(school.get("postal_code"))
    city = _text(school.get("city"))

    street_line = " ".join(part for part in (street, street_nr) if part)
    city_line = " ".join(part for part in (postal_code, city) if part)
    return ", ".join(part for part in (street_line, city_line) if part) or None


def school_coordinates_from_data(data: Any) -> tuple[float, float] | None:
    """Find school coordinates from API data or known public school metadata."""
    school = _school_data(data)
    if not isinstance(school, dict):
        return None

    latitude = school.get("latitude") or school.get("lat")
    longitude = school.get("longitude") or school.get("lon") or school.get("lng")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return float(latitude), float(longitude)

    school_id = school.get("id")
    if isinstance(school_id, int) and school_id in KNOWN_SCHOOL_COORDINATES:
        return KNOWN_SCHOOL_COORDINATES[school_id]

    return None


def _school_data(data: Any) -> dict[str, Any] | None:
    """Return the nested school data dict if present."""
    if not isinstance(data, dict):
        return None

    school = data.get("school", data)
    if isinstance(school, dict) and isinstance(school.get("data"), dict):
        return school["data"]
    if isinstance(school, dict):
        return school
    return None


def student_data_from_data(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the student represented by this data block."""
    selected = data.get("selected_student")
    if isinstance(selected, dict):
        return selected

    students = data.get("students")
    if isinstance(students, dict):
        value = students.get("data")
        if isinstance(value, list):
            return next((item for item in value if isinstance(item, dict)), None)
        if isinstance(value, dict):
            return value
    if isinstance(students, list):
        return next((item for item in students if isinstance(item, dict)), None)
    return None


def student_id_from_data(data: dict[str, Any]) -> str:
    """Return a stable student id for entity and device identifiers."""
    student = student_data_from_data(data)
    if isinstance(student, dict) and student.get("id") is not None:
        return str(student["id"])
    return "student"


def student_name_from_data(data: dict[str, Any]) -> str | None:
    """Return a readable student name, preferring the first name."""
    student = student_data_from_data(data)
    if not isinstance(student, dict):
        return None

    for key in ("forename", "firstName", "first_name", "nickname", "givenName"):
        text = _text(student.get(key))
        if text:
            return text

    full_name = _text(student.get("displayName")) or _text(student.get("full_name"))
    if full_name:
        return full_name.split()[0]

    return _text(student.get("name"))


def besteschule_device_info(entry: ConfigEntry, data: dict[str, Any]) -> DeviceInfo:
    """Return Home Assistant device info for beste.schule entities."""
    school_name = school_name_from_data(data) or entry.data.get(CONF_SCHOOL_NAME)
    student_id = str(data.get("identifier_student_id") or student_id_from_data(data))
    student_name = student_name_from_data(data) or entry.title
    identifier = f"{entry.entry_id}:{student_id}"
    return DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        manufacturer="beste.schule",
        model=school_name or "beste.schule",
        name=student_name,
        configuration_url="https://beste.schule",
    )
