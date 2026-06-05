"""Small async client for the beste.schule API."""

from __future__ import annotations

from datetime import timedelta
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
            "user-management/me",
            "me",
            "users/me",
            "students",
            "children",
            "pupils",
            "persons",
            "groups",
            "years",
            "status",
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
            "user-management/me",
            "me",
            "users/me",
        )

        for route in routes:
            try:
                return await self.request(route)
            except BesteSchuleApiError:
                continue
        return None

    async def fetch_overview(self) -> dict[str, Any]:
        """Fetch the first read-only routes we want to explore."""
        data: dict[str, Any] = {}

        for key, (route, params) in {
            "me": ("user-management/me", None),
            "school": ("school", None),
            "students": ("students", None),
        }.items():
            try:
                data[key] = await self.request(route, params=params)
            except BesteSchuleApiError as err:
                data[key] = {"error": str(err)}

        student_id = _student_id_from_data(data.get("students"))
        range_start = dt_util.now().date() - timedelta(days=7)
        range_end = dt_util.now().date() + timedelta(days=60)

        routes = {
            "time_tables": (
                "time-tables",
                {
                    "include": (
                        "times,lessons,subject,subjects,room,rooms,teacher,"
                        "teachers,group,groups"
                    )
                },
            ),
            "time_tables_current": ("time-tables/current", None),
            "time_tables_show_current": ("time-tables/showCurrent", None),
            "time_tables_show_current_kebab": ("time-tables/show-current", None),
            "time_table_times": (
                "time-table-times",
                {"include": "lessons,subject,room,teacher,group"},
            ),
            "time_table_time_lessons": (
                "time-table-time-lessons",
                {"include": "subject,room,teacher,group,time"},
            ),
            "journal_days": (
                "journal/days",
                {"include": "lessons,subject,room,teacher,group,time"},
            ),
            "journal_weeks": (
                "journal/weeks",
                {"include": "days,lessons,subject,room,teacher,group,time"},
            ),
            "journal_lessons": (
                "journal/lessons",
                {"include": "day,subject,room,teacher,group,time"},
            ),
            "journal_lesson_student": (
                "journal/lesson-student",
                None,
            ),
            "journal_day_student": (
                "journal/day-student",
                None,
            ),
            "substitution_days": ("substitution-plans/days", None),
            "announcements": ("announcements", None),
            "checklists": ("checklists", None),
            "grades": ("grades", None),
            "finalgrades": ("finalgrades", None),
        }
        if student_id is not None:
            routes["journal_lessons_student"] = (
                "journal/lessons",
                {
                    "include": "day,subject,teachers,group,notes.type",
                    "filter[student]": student_id,
                    "filter[range]": f"{range_start.isoformat()},{range_end.isoformat()}",
                },
            )
        else:
            data["journal_lessons_student"] = {"error": "Could not determine student id"}

        for key, (route, params) in routes.items():
            try:
                data[key] = await self.request(route, params=params)
            except BesteSchuleApiError as err:
                data[key] = {"error": str(err)}
        return data


def _student_id_from_data(data: Any) -> int | str | None:
    """Extract the first student id from common API response shapes."""
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return _student_id_from_data(data["data"])

    if isinstance(data, list):
        for item in data:
            student_id = _student_id_from_data(item)
            if student_id is not None:
                return student_id
        return None

    if not isinstance(data, dict):
        return None

    for key in ("id", "student_id", "studentId"):
        value = data.get(key)
        if isinstance(value, (int, str)) and str(value).strip():
            return value

    for key in ("student", "child", "pupil"):
        student_id = _student_id_from_data(data.get(key))
        if student_id is not None:
            return student_id

    return None
