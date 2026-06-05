"""Small async client for the beste.schule API."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


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
        routes = {
            "me": ("user-management/me", None),
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
            "time_table_times": (
                "time-table-times",
                {"include": "lessons,subject,room,teacher,group"},
            ),
            "time_table_time_lessons": (
                "time-table-time-lessons",
                {"include": "subject,room,teacher,group,time"},
            ),
            "substitution_days": ("substitution-plans/days", None),
            "announcements": ("announcements", None),
            "checklists": ("checklists", None),
            "grades": ("grades", None),
            "finalgrades": ("finalgrades", None),
        }

        data: dict[str, Any] = {}
        for key, (route, params) in routes.items():
            try:
                data[key] = await self.request(route, params=params)
            except BesteSchuleApiError as err:
                data[key] = {"error": str(err)}
        return data
