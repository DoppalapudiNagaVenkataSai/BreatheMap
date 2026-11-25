"""Unit and integration tests for data providers, demo mode, and air service."""

import pytest
import respx
from httpx import AsyncClient, Response

from app.domain.models import LatLon, Scale
from app.providers.demo import DemoProvider
from app.providers.nominatim import NominatimAdapter
from app.providers.open_meteo_air import OPEN_METEO_AIR_URL, OpenMeteoAirAdapter
from app.providers.open_meteo_weather import OPEN_METEO_FORECAST_URL, OpenMeteoWeatherAdapter
from app.services.air_service import AirService


@pytest.mark.asyncio
async def test_demo_provider_offline() -> None:
    demo = DemoProvider()
    loc = LatLon(lat=28.6315, lon=77.2167)

    air = await demo.get_air(loc)
    assert air.get("synthetic") is True
    assert "hourly" in air

    weather = await demo.get_weather(loc)
    assert weather.get("synthetic") is True

    places = await demo.search("Connaught")
    assert len(places) > 0
    assert "Connaught" in places[0]["label"]

    rev = await demo.reverse(28.6315, 77.2167)
    assert rev is not None


@pytest.mark.asyncio
async def test_air_service_demo_flow() -> None:
    demo = DemoProvider()
    service = AirService(demo, demo)
    loc = LatLon(lat=28.6315, lon=77.2167)

    res = await service.get_air(loc, scale=Scale.NAQI, is_demo=True)
    assert res["provenance"]["is_demo"] is True
    assert res["band"] != ""
    assert "pm25" in res["pollutants"]
    assert res["windows"]["cleanest"] is not None


@pytest.mark.asyncio
@respx.mock
async def test_open_meteo_adapters_respx(client: AsyncClient) -> None:
    mock_air_res = {
        "current": {"pm2_5": 85.0, "pm10": 120.0, "us_aqi": 160},
        "hourly": {
            "time": ["2026-11-25T10:00", "2026-11-25T11:00", "2026-11-25T12:00"],
            "pm2_5": [80.0, 85.0, 90.0],
            "pm10": [110.0, 120.0, 130.0],
        },
    }
    mock_weather_res = {
        "daily": {"sunrise": ["2026-11-25T06:30"], "sunset": ["2026-11-25T17:30"]},
        "hourly": {
            "temperature_2m": [22.0],
            "relative_humidity_2m": [50],
            "wind_speed_10m": [5.0],
            "precipitation": [0.0],
        },
    }

    respx.get(OPEN_METEO_AIR_URL).mock(return_value=Response(200, json=mock_air_res))
    respx.get(OPEN_METEO_FORECAST_URL).mock(return_value=Response(200, json=mock_weather_res))

    air_adapter = OpenMeteoAirAdapter(client)
    weather_adapter = OpenMeteoWeatherAdapter(client)
    loc = LatLon(lat=28.6, lon=77.2)

    air_data = await air_adapter.get_air(loc)
    assert air_data["current"]["pm2_5"] == 85.0

    weather_data = await weather_adapter.get_weather(loc)
    assert weather_data["daily"]["sunrise"] == ["2026-11-25T06:30"]


@pytest.mark.asyncio
@respx.mock
async def test_nominatim_search_and_reverse(client: AsyncClient) -> None:
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=Response(
            200,
            json=[
                {
                    "display_name": "Connaught Place, New Delhi",
                    "lat": "28.6315",
                    "lon": "77.2167",
                    "address": {"country_code": "in"},
                }
            ],
        )
    )
    respx.get("https://nominatim.openstreetmap.org/reverse").mock(
        return_value=Response(
            200,
            json={
                "display_name": "Connaught Place, New Delhi",
                "lat": "28.6315",
                "lon": "77.2167",
                "address": {"country_code": "in"},
            },
        )
    )

    nom = NominatimAdapter(client)
    results = await nom.search("Connaught Place")
    assert len(results) == 1
    assert results[0]["country_code"] == "in"

    rev = await nom.reverse(28.6315, 77.2167)
    assert rev is not None
    assert rev["label"] == "Connaught Place, New Delhi"


@pytest.mark.asyncio
async def test_api_air_and_geo_endpoints(client: AsyncClient) -> None:
    # Air endpoint with demo header
    res_air = await client.get(
        "/api/v1/air?lat=28.6315&lon=77.2167&scale=naqi",
        headers={"X-BreatheMap-Demo": "true"},
    )
    assert res_air.status_code == 200
    data = res_air.json()["data"]
    assert data["provenance"]["is_demo"] is True
    assert data["scale"] == "naqi"

    # Geocode with demo header
    res_geo = await client.get(
        "/api/v1/geocode?q=Connaught",
        headers={"X-BreatheMap-Demo": "true"},
    )
    assert res_geo.status_code == 200
    places = res_geo.json()["data"]
    assert len(places) > 0

    # Reverse geocode with demo header
    res_rev = await client.get(
        "/api/v1/reverse?lat=28.6315&lon=77.2167",
        headers={"X-BreatheMap-Demo": "true"},
    )
    assert res_rev.status_code == 200
