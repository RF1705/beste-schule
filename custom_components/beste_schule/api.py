"""Small async client for the beste.schule API."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientResponseError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class BesteSchuleApiError(Exception):
    """Raised when the beste.schule API request fails."""


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
            raise BesteSchuleApiError(
                f"beste.schule returned HTTP {err.status} for {route}"
            ) from err
        except Exception as err:
            raise BesteSchuleApiError(f"Could not request beste.schule route {route}") from err

    async def validate_token(self) -> None:
        """Validate that the token can access the current user endpoint."""
        await self.request("user-management/me")

    async def fetch_overview(self) -> dict[str, Any]:
        """Fetch the first read-only routes we want to explore."""
        routes = {
            "me": ("user-management/me", None),
            "time_tables": ("time-tables", None),
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
