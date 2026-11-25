"""Integration tests for ORS, OSRM, and Overpass adapters using respx."""

import pytest
import respx
from httpx import AsyncClient, Response

from app.core.errors import ProviderUnavailableError
from app.domain.models import LatLon, Mode
from app.providers.ors import ORS_BASE_URL, ORSAdapter
from app.providers.osrm import OSRM_BASE_URL, OSRMAdapter
from app.providers.overpass import OVERPASS_URL, OverpassAdapter


@pytest.mark.asyncio
@respx.mock
async def test_ors_adapter_success_and_waytypes() -> None:
    mock_geojson = {
        "features": [
            {
                "geometry": {
                    "coordinates": [[77.2167, 28.6315], [77.2180, 28.6350], [77.2194, 28.6430]]
                },
                "properties": {
                    "summary": {"distance": 1650.0, "duration": 1188.0},
                    "extras": {"waytype": {"values": [[0, 1, 7], [1, 2, 1]]}},
                },
            }
        ]
    }
    respx.post(f"{ORS_BASE_URL}/foot-walking/geojson").mock(
        return_value=Response(200, json=mock_geojson)
    )

    async with AsyncClient() as cli:
        adapter = ORSAdapter(cli, api_key="test-key")
        routes = await adapter.get_routes(
            LatLon(lat=28.6315, lon=77.2167),
            LatLon(lat=28.6430, lon=77.2194),
            Mode.WALK,
        )
        assert len(routes) == 1
        assert routes[0].distance_m == 1650.0
        assert routes[0].geometry.coordinates[0] == (28.6315, 77.2167)
        assert routes[0].geometry.waytypes == ["footway", "state"]


@pytest.mark.asyncio
@respx.mock
async def test_ors_adapter_429_raises_unavailable() -> None:
    respx.post(f"{ORS_BASE_URL}/driving-car/geojson").mock(return_value=Response(429))

    async with AsyncClient() as cli:
        adapter = ORSAdapter(cli, api_key="test-key")
        with pytest.raises(ProviderUnavailableError):
            await adapter.get_routes(
                LatLon(lat=28.6315, lon=77.2167),
                LatLon(lat=28.6430, lon=77.2194),
                Mode.CAR,
            )


@pytest.mark.asyncio
@respx.mock
async def test_osrm_adapter_success_and_error() -> None:
    mock_osrm = {
        "code": "Ok",
        "routes": [
            {
                "distance": 1700.0,
                "duration": 420.0,
                "geometry": {"coordinates": [[77.2167, 28.6315], [77.2194, 28.6430]]},
            }
        ],
    }
    respx.get(f"{OSRM_BASE_URL}/routed-bike/route/v1/bike/77.2167,28.6315;77.2194,28.643").mock(
        return_value=Response(200, json=mock_osrm)
    )

    async with AsyncClient() as cli:
        adapter = OSRMAdapter(cli)
        routes = await adapter.get_routes(
            LatLon(lat=28.6315, lon=77.2167),
            LatLon(lat=28.6430, lon=77.2194),
            Mode.CYCLE,
        )
        assert len(routes) == 1
        assert routes[0].geometry.waytypes is None


@pytest.mark.asyncio
@respx.mock
async def test_overpass_adapter_lighting() -> None:
    mock_overpass = {
        "elements": [
            {
                "type": "way",
                "tags": {"highway": "residential", "lit": "yes"},
                "geometry": [{"lat": 28.6315, "lon": 77.2167}, {"lat": 28.6340, "lon": 77.2175}],
            }
        ]
    }
    respx.post(OVERPASS_URL).mock(return_value=Response(200, json=mock_overpass))

    async with AsyncClient() as cli:
        adapter = OverpassAdapter(cli)
        ways = await adapter.get_lighting_ways([(28.6315, 77.2167), (28.6430, 77.2194)])
        assert len(ways) == 1
        assert ways[0]["lit"] == "yes"
