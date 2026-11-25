"""Tests for BreatheRoute comparison service and POST /api/v1/routes/compare."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.errors import ProviderUnavailableError, ValidationAppError
from app.domain.models import LatLon, Mode, SortOption
from app.providers.base import RawRoute, RoutingProvider
from app.providers.demo import DemoProvider
from app.services.route_service import RouteService


class FailingRouter(RoutingProvider):
    async def get_routes(self, origin: LatLon, destination: LatLon, mode: Mode) -> list[RawRoute]:
        raise ProviderUnavailableError("Simulated failure")


@pytest.mark.asyncio
async def test_route_compare_demo_api_night_trip(client: AsyncClient) -> None:
    # 22:00 IST = 16:30 UTC (sunset in delhi_weather.json is 17:24; let's use 18:00 UTC)
    payload: dict[str, Any] = {
        "origin_text": "Connaught Place",
        "destination_text": "New Delhi Railway Station",
        "departure_time": "2026-11-25T18:00:00Z",
        "flexibility_minutes": 120,
        "sort": "least_pollution",
        "prefer_lit": True,
    }
    res = await client.post(
        "/api/v1/routes/compare",
        json=payload,
        headers={"X-BreatheMap-Demo": "true"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["provenance"]["is_demo"] is True
    assert len(data["options"]) == 6
    assert data["best_option"] is not None
    assert data["fastest_option"] is not None


@pytest.mark.asyncio
async def test_route_compare_validation_errors(client: AsyncClient) -> None:
    # Same origin & destination (< 100 m)
    res_same = await client.post(
        "/api/v1/routes/compare",
        json={
            "origin": {"lat": 28.6315, "lon": 77.2167},
            "destination": {"lat": 28.6316, "lon": 77.2167},
        },
        headers={"X-BreatheMap-Demo": "true"},
    )
    assert res_same.status_code == 422
    assert "already there" in res_same.json()["error"]["message"].lower()

    # Distance > 100 km
    res_far = await client.post(
        "/api/v1/routes/compare",
        json={
            "origin": {"lat": 28.6315, "lon": 77.2167},
            "destination": {"lat": 27.1751, "lon": 78.0421},  # Agra (~180 km)
        },
        headers={"X-BreatheMap-Demo": "true"},
    )
    assert res_far.status_code == 422
    assert "100 km" in res_far.json()["error"]["message"]

    # Extra forbidden field
    res_extra = await client.post(
        "/api/v1/routes/compare",
        json={
            "origin": {"lat": 28.6315, "lon": 77.2167},
            "destination": {"lat": 28.6430, "lon": 77.2194},
            "unexpected_field": 123,
        },
        headers={"X-BreatheMap-Demo": "true"},
    )
    assert res_extra.status_code == 422


@pytest.mark.asyncio
async def test_route_service_fallback_and_time_rules() -> None:
    demo = DemoProvider()
    svc = RouteService(
        air_provider=demo,
        weather_provider=demo,
        geo_provider=demo,
        primary_router=FailingRouter(),
        fallback_router=demo,
        lighting_provider=demo,
    )
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)

    # Past departure (> 10 min ago) -> uses now with warning
    res_past = await svc.compare(
        origin_coord=LatLon(lat=28.6315, lon=77.2167),
        dest_coord=LatLon(lat=28.6430, lon=77.2194),
        departure_time=now - timedelta(hours=1),
        sort_by=SortOption.BALANCED,
        is_demo=True,
        now=now,
    )
    warnings = res_past["provenance"]["warnings"]
    assert any("past" in w.lower() for w in warnings)
    assert any("fallback" in w.lower() for w in warnings)

    # Beyond 48h -> ValidationAppError
    with pytest.raises(ValidationAppError):
        await svc.compare(
            origin_coord=LatLon(lat=28.6315, lon=77.2167),
            dest_coord=LatLon(lat=28.6430, lon=77.2194),
            departure_time=now + timedelta(hours=49),
            now=now,
        )


@pytest.mark.asyncio
async def test_route_service_both_routers_down_keeps_metro() -> None:
    demo = DemoProvider()
    svc = RouteService(
        air_provider=demo,
        weather_provider=demo,
        geo_provider=demo,
        primary_router=FailingRouter(),
        fallback_router=FailingRouter(),
        lighting_provider=demo,
    )
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    res = await svc.compare(
        origin_coord=LatLon(lat=28.6315, lon=77.2167),
        dest_coord=LatLon(lat=28.6430, lon=77.2194),
        departure_time=now,
        now=now,
    )
    metro_opts = [o for o in res["options"] if o["mode"] == "metro"]
    assert len(metro_opts) == 1
    assert metro_opts[0]["status"] == "available"
    walk_opts = [o for o in res["options"] if o["mode"] == "walk"]
    assert walk_opts[0]["status"] == "unavailable"
