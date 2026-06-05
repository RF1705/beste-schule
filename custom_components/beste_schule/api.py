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

    async def fetch_overview(self) -> dict[str, Any]:
        """Fetch the first read-only routes we want to explore."""
        data: dict[str, Any] = {}

        for key, (route, params) in {
            "school": ("school", None),
            "students": ("students", None),
        }.items():
            try:
                data[key] = await self.request(route, params=params)
            except BesteSchuleApiError as err:
                data[key] = {"error": str(err)}

        range_start = dt_util.now().date() - timedelta(days=7)
        range_end = dt_util.now().date() + timedelta(days=60)

        routes = {
            "time_tables_current": ("time-tables/current", None),
            "journal_weeks": (
                (
                    "journal/weeks",
                    {
                        "include": (
                            "days,days.notes,days.notes.type,lessons,lessons.notes,"
                            "lessons.notes.type,subject,room,teacher,group,time,notes,notes.type"
                        )
                    },
                ),
                (
                    "journal/weeks",
                    {"include": "days,lessons,subject,room,teacher,group,time"},
                ),
            ),
            "journal_lesson_student": (
                (
                    "journal/lesson-student",
                    {"include": "lesson,lesson.day,lesson.subject,notes,notes.type"},
                ),
                ("journal/lesson-student", None),
            ),
            "journal_day_student": (
                "journal/day-student",
                None,
            ),
            "substitution_days": (
                "substitution-plans/days",
                {
                    "include": "lessons,subject,teachers,rooms,notes",
                    "filter[range]": f"{range_start.isoformat()},{range_end.isoformat()}",
                    "per_page": 100,
                },
            ),
            "grades": (
                ("grades", {"include": "collection"}),
                ("grades", None),
            ),
            "finalgrades": ("finalgrades", None),
        }

        for key, route_info in routes.items():
            data[key] = await self._request_first_available(route_info)
        return data

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
