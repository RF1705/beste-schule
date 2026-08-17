"""Tests for beste.schule API error, cache, and concurrency handling."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.beste_schule.api import (
    BesteSchuleApi,
    BesteSchuleApiError,
    BesteSchuleAuthError,
    _is_error_response,
)


@pytest.mark.asyncio
async def test_first_available_propagates_auth_error() -> None:
    """Authentication failures must reach the config entry coordinator."""
    api = object.__new__(BesteSchuleApi)
    api.request = AsyncMock(side_effect=BesteSchuleAuthError("invalid token"))

    with pytest.raises(BesteSchuleAuthError):
        await api._request_first_available(("school", None))


@pytest.mark.asyncio
async def test_optional_endpoint_returns_error_response() -> None:
    """An unavailable optional endpoint retains a useful error payload."""
    api = object.__new__(BesteSchuleApi)
    api.request = AsyncMock(side_effect=BesteSchuleApiError("offline"))

    response = await api._request_first_available(("school", None))

    assert _is_error_response(response)
    assert response == {"error": "offline"}


@pytest.mark.asyncio
async def test_shared_response_cache_returns_independent_copies() -> None:
    """Filtering one child's data must not mutate another child's cached response."""
    api = object.__new__(BesteSchuleApi)
    api._response_cache = {}
    api._request_first_available = AsyncMock(
        return_value={"data": [{"id": 1}, {"id": 2}]}
    )

    first = await api._request_first_available_cached(
        ("students", None),
        cache_key="students",
        max_age=60,
    )
    first["data"].pop()
    second = await api._request_first_available_cached(
        ("students", None),
        cache_key="students",
        max_age=60,
    )

    assert second == {"data": [{"id": 1}, {"id": 2}]}
    api._request_first_available.assert_awaited_once_with(("students", None))


@pytest.mark.asyncio
async def test_independent_routes_start_concurrently() -> None:
    """Independent endpoints should not wait for one another."""
    api = object.__new__(BesteSchuleApi)
    started = {"first": asyncio.Event(), "second": asyncio.Event()}
    release = asyncio.Event()

    async def request_route(route_info):
        route = route_info[0]
        started[route].set()
        await release.wait()
        return {"route": route}

    api._request_first_available = request_route
    task = asyncio.create_task(
        api._request_routes(
            {
                "a": ("first", None),
                "b": ("second", None),
            }
        )
    )
    await asyncio.wait_for(
        asyncio.gather(*(event.wait() for event in started.values())),
        timeout=1,
    )
    release.set()

    assert await task == {
        "a": {"route": "first"},
        "b": {"route": "second"},
    }


@pytest.mark.asyncio
async def test_finalgrade_detail_propagates_auth_error() -> None:
    """Detail requests must also trigger Home Assistant's reauthentication flow."""
    api = object.__new__(BesteSchuleApi)
    api._finalgrade_detail_cache = {}
    api.request = AsyncMock(side_effect=BesteSchuleAuthError("invalid token"))

    with pytest.raises(BesteSchuleAuthError):
        await api._fetch_finalgrade_details([{"id": 42}])


@pytest.mark.asyncio
async def test_fetch_overview_requests_timetable_lesson_times() -> None:
    """The current timetable must explicitly include per-lesson times."""
    api = object.__new__(BesteSchuleApi)
    api._response_cache = {}
    api._request_first_available_cached = AsyncMock(return_value={"data": []})
    api._request_routes = AsyncMock(return_value={})
    api._fetch_finalgrade_details = AsyncMock(return_value={})
    api._fetch_grade_years = AsyncMock(return_value={})

    await api.fetch_overview(students={"data": [{"id": 1}]})

    assert any(
        args[0] == ("time-tables/current", {"include": "lessons.times"})
        and kwargs.get("cache_key") == "time_tables_current"
        for args, kwargs in api._request_first_available_cached.call_args_list
    )
