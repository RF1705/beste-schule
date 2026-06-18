"""Small async client for the beste.schule API."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import re
from typing import Any

from aiohttp import ClientError, ClientResponseError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util


class BesteSchuleApiError(Exception):
    """Raised when the beste.schule API request fails."""


class BesteSchuleAuthError(BesteSchuleApiError):
    """Raised when beste.schule rejects the token."""


class BesteSchuleApi:
    """Client for read-only beste.schule API calls."""

    def __init__(self, hass: HomeAssistant, api_url: str, token: str) -> None:
        self._session = async_get_clientsession(hass)
        self._api_url = api_url.rstrip("/")
        self._token = token

    async def request(
        self,
        route: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Request a route below the configured API URL."""
        url = f"{self._api_url}/{route.lstrip('/')}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

        try:
            response = await self._session.get(url, headers=headers, params=params)
            response.raise_for_status()
            return await response.json()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise BesteSchuleAuthError(
                    f"beste.schule rejected the token for {route}"
                ) from err
            raise BesteSchuleApiError(
                f"beste.schule returned HTTP {err.status} for {route}"
            ) from err
        except ClientError as err:
            raise BesteSchuleApiError(f"Could not request beste.schule route {route}") from err

    async def validate_token(self) -> Any:
        """Validate that the token can access at least one known read-only route."""
        routes = (
            "students",
            "school",
            "time-tables/current",
        )
        last_error: BesteSchuleApiError | None = None
        saw_auth_error = False

        for route in routes:
            try:
                return await self.request(route)
            except BesteSchuleAuthError as err:
                saw_auth_error = True
                last_error = err
            except BesteSchuleApiError as err:
                last_error = err

        if saw_auth_error:
            raise BesteSchuleAuthError("beste.schule rejected the token") from last_error
        raise BesteSchuleApiError("Could not validate the beste.schule token") from last_error

    async def fetch_suggested_name_data(self) -> Any:
        """Fetch optional profile data for a useful Home Assistant device name."""
        routes = (
            "students",
            "children",
            "pupils",
        )

        for route in routes:
            try:
                return await self.request(route)
            except BesteSchuleApiError:
                continue
        return None

    async def fetch_students(self) -> Any:
        """Fetch students available for the token."""
        return await self.request("students")

    async def fetch_overview(
        self,
        student: dict[str, Any] | None = None,
        students: Any | None = None,
    ) -> dict[str, Any]:
        """Fetch the first read-only routes we want to explore."""
        data: dict[str, Any] = {}

        try:
            data["school"] = await self.request("school")
        except BesteSchuleApiError as err:
            data["school"] = {"error": str(err)}

        data["students"] = (
            students
            if students is not None
            else await self._request_first_available(("students", None))
        )
        data["multi_student"] = _student_count(data["students"]) > 1
        if student is not None:
            data["selected_student"] = student

        substitution_range_start = dt_util.now().date() - timedelta(days=7)
        substitution_range_end = dt_util.now().date() + timedelta(days=60)
        homework_range_start = dt_util.now().date()
        homework_range_end = dt_util.now().date() + timedelta(days=21)
        student_id = (
            student.get("id")
            if isinstance(student, dict)
            else _first_student_id(data.get("students"))
        )
        student_filter = {"filter[student]": student_id} if student_id is not None else {}

        routes = {
            "groups": (
                "groups",
                {
                    **student_filter,
                    "include": "students",
                    "per_page": 100,
                },
            ),
            "time_tables_current": ("time-tables/current", None),
            "journal_weeks": (
                (
                    "journal/weeks",
                    {
                        **student_filter,
                        "include": (
                            "days,days.notes,days.notes.type,lessons,lessons.notes,"
                            "lessons.notes.type,subject,room,teacher,group,time,notes,notes.type"
                        )
                    },
                ),
                (
                    "journal/weeks",
                    {
                        **student_filter,
                        "include": "days,lessons,subject,room,teacher,group,time",
                    },
                ),
            ),
            "journal_lesson_student": (
                (
                    "journal/lesson-student",
                    {
                        **student_filter,
                        "include": "lesson,lesson.day,lesson.subject,notes,notes.type",
                    },
                ),
                ("journal/lesson-student", student_filter or None),
            ),
            "journal_day_student": (
                "journal/day-student",
                student_filter or None,
            ),
            "substitution_days": (
                "substitution-plans/days",
                {
                    "include": "lessons,subject,teachers,rooms,notes",
                    "filter[range]": (
                        f"{substitution_range_start.isoformat()},"
                        f"{substitution_range_end.isoformat()}"
                    ),
                    "per_page": 250,
                },
            ),
            "grades": (
                ("grades", {**student_filter, "include": "collection"}),
                ("grades", student_filter or None),
            ),
            "finalgrades": ("finalgrades", student_filter or None),
        }
        if student_id is not None:
            routes["journal_lessons"] = (
                "journal/lessons",
                {
                    "include": "notes.type",
                    "filter[student]": student_id,
                    "filter[range]": (
                        f"{homework_range_start.isoformat()},"
                        f"{homework_range_end.isoformat()}"
                    ),
                    "per_page": 100,
                },
            )

        for key, route_info in routes.items():
            data[key] = await self._request_first_available(route_info)
        data["finalgrade_details"] = await self._fetch_finalgrade_details(
            data.get("finalgrades")
        )
        if student is not None:
            _filter_overview_for_student(data, student)
        return data

    async def _fetch_finalgrade_details(self, finalgrades: Any) -> dict[str, Any]:
        """Fetch every finalgrade detail response with limited concurrency."""
        items = (
            finalgrades.get("data")
            if isinstance(finalgrades, dict)
            else finalgrades
        )
        if not isinstance(items, list):
            return {}

        ids = {
            str(item["id"])
            for item in items
            if isinstance(item, dict) and item.get("id") is not None
        }
        semaphore = asyncio.Semaphore(4)

        async def fetch(finalgrade_id: str) -> tuple[str, Any]:
            async with semaphore:
                try:
                    response = await self.request(f"finalgrades/{finalgrade_id}")
                except BesteSchuleApiError as err:
                    response = {"error": str(err)}
                return finalgrade_id, response

        return dict(await asyncio.gather(*(fetch(value) for value in sorted(ids))))

    async def _request_first_available(
        self,
        route_info: tuple[str, dict[str, Any] | None]
        | tuple[tuple[str, dict[str, Any] | None], ...],
    ) -> Any:
        """Request a route, optionally trying fallback route/parameter pairs."""
        requests = (
            (route_info,)
            if isinstance(route_info[0], str)
            else route_info
        )
        last_error: BesteSchuleApiError | None = None
        for request_route, request_params in requests:
            try:
                return await self.request(request_route, params=request_params)
            except BesteSchuleApiError as err:
                last_error = err

        return {
            "error": str(last_error)
            if last_error
            else "Unknown beste.schule API error"
        }


def _first_student_id(students: Any) -> int | str | None:
    """Return the first student id from a students API response."""
    if isinstance(students, dict):
        data = students.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id") is not None:
                    return item["id"]
        if isinstance(data, dict) and data.get("id") is not None:
            return data["id"]
    if isinstance(students, list):
        for item in students:
            if isinstance(item, dict) and item.get("id") is not None:
                return item["id"]
    return None


def _student_count(students: Any) -> int:
    """Return the number of students in a students API response."""
    if isinstance(students, dict):
        data = students.get("data")
        if isinstance(data, list):
            return len([item for item in data if isinstance(item, dict)])
        if isinstance(data, dict):
            return 1
    if isinstance(students, list):
        return len([item for item in students if isinstance(item, dict)])
    return 0


def _filter_overview_for_student(data: dict[str, Any], student: dict[str, Any]) -> None:
    """Keep only data that belongs to the selected student where the API returns mixed data."""
    student_context = _student_context_with_groups(student, data.get("groups"))
    _filter_timetable(data.get("time_tables_current"), student_context)
    _filter_substitution_days(data.get("substitution_days"), student_context)
    _filter_journal_weeks(data.get("journal_weeks"), student_context)
    for key in ("journal_lesson_student", "journal_day_student", "grades", "finalgrades"):
        _filter_data_list(data.get(key), student_context)


def _student_context_with_groups(
    student: dict[str, Any],
    groups_response: Any,
) -> dict[str, Any]:
    """Return student data enriched with groups from the groups API."""
    context = dict(student)
    existing = student.get("meta_groups")
    groups = [
        group
        for group in _response_data(groups_response) or []
        if isinstance(group, dict)
    ]
    if isinstance(existing, list):
        groups = [*existing, *groups]

    unique_groups: dict[str, dict[str, Any]] = {}
    for group in groups:
        key = str(group.get("id") or group.get("local_id") or group.get("name"))
        unique_groups[key] = group
    context["meta_groups"] = list(unique_groups.values())
    return context


def _filter_timetable(value: Any, student: dict[str, Any]) -> None:
    """Filter timetable lessons by the student's class/group."""
    body = _response_data(value)
    if not isinstance(body, dict) or not isinstance(body.get("lessons"), list):
        return
    body["lessons"] = [
        item for item in body["lessons"] if _item_matches_student_context(item, student)
    ]


def _filter_substitution_days(value: Any, student: dict[str, Any]) -> None:
    """Filter substitution lessons by the student's class/group."""
    days = _response_data(value)
    if not isinstance(days, list):
        return
    for day in days:
        if not isinstance(day, dict) or not isinstance(day.get("lessons"), list):
            continue
        day["lessons"] = [
            item for item in day["lessons"] if _item_matches_student_context(item, student)
        ]


def _filter_journal_weeks(value: Any, student: dict[str, Any]) -> None:
    """Filter nested journal week lesson lists by the student's class/group."""
    weeks = _response_data(value)
    if not isinstance(weeks, list):
        return
    for week in weeks:
        _filter_nested_lesson_lists(week, student)


def _filter_nested_lesson_lists(value: Any, student: dict[str, Any]) -> None:
    """Filter any nested key named lessons in-place."""
    if isinstance(value, dict):
        lessons = value.get("lessons")
        if isinstance(lessons, list):
            value["lessons"] = [
                item for item in lessons if _item_matches_student_context(item, student)
            ]
        for nested in value.values():
            _filter_nested_lesson_lists(nested, student)
    elif isinstance(value, list):
        for item in value:
            _filter_nested_lesson_lists(item, student)


def _filter_data_list(value: Any, student: dict[str, Any]) -> None:
    """Filter a top-level data list by student id when items carry student details."""
    items = _response_data(value)
    if not isinstance(items, list):
        return
    known = [item for item in items if _item_student_id(item) is not None]
    if not known:
        return
    student_id = str(student.get("id"))
    items[:] = [item for item in items if _item_student_id(item) == student_id]


def _response_data(value: Any) -> Any:
    """Return the data payload for common API response shapes."""
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def _item_matches_student_context(item: Any, student: dict[str, Any]) -> bool:
    """Return whether an item belongs to the selected student or has no useful context."""
    item_student_id = _item_student_id(item)
    if item_student_id is not None:
        return item_student_id == str(student.get("id"))

    group_values = _student_group_values(student)
    item_groups = _item_group_values(item)
    if item_groups:
        return bool(group_values & item_groups) or _matches_student_subgroup(
            group_values,
            item_groups,
        )
    return True


def _matches_student_subgroup(
    student_groups: set[str],
    item_groups: set[str],
) -> bool:
    """Return whether a subject group belongs to the student's main class."""
    class_signatures = {
        match.groups()
        for value in student_groups
        if (match := re.fullmatch(r"(\d+)\s*([a-z])", value))
    }
    if not class_signatures:
        return False

    for value in item_groups:
        compact = re.sub(r"[^a-z0-9]", "", value)
        for year, class_letter in class_signatures:
            if compact.startswith(year) and compact.endswith(class_letter):
                return True
    return False


def _item_student_id(value: Any) -> str | None:
    """Return a nested student id if present."""
    if isinstance(value, dict):
        student = value.get("student")
        if isinstance(student, dict) and student.get("id") is not None:
            return str(student["id"])
        if value.get("student_id") is not None:
            return str(value["student_id"])
        for nested in value.values():
            found = _item_student_id(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _item_student_id(item)
            if found is not None:
                return found
    return None


def _student_group_values(student: dict[str, Any]) -> set[str]:
    """Return ids and names for the student's groups/classes."""
    values: set[str] = set()
    groups = student.get("meta_groups")
    if isinstance(groups, list):
        for group in groups:
            if isinstance(group, dict):
                values.update(_group_values(group))
    return values


def _item_group_values(value: Any) -> set[str]:
    """Return nested group ids and names from an item."""
    values: set[str] = set()
    if isinstance(value, dict):
        group = value.get("group")
        if isinstance(group, dict):
            values.update(_group_values(group))
        groups = value.get("groups")
        if isinstance(groups, list):
            for item in groups:
                if isinstance(item, dict):
                    values.update(_group_values(item))
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                values.update(_item_group_values(nested))
    elif isinstance(value, list):
        for item in value:
            values.update(_item_group_values(item))
    return values


def _group_values(group: dict[str, Any]) -> set[str]:
    """Return stable comparable values for a group relation."""
    values: set[str] = set()
    for key in ("id", "local_id", "name"):
        value = group.get(key)
        if value is not None:
            values.add(str(value).strip().lower())
    return {value for value in values if value}
