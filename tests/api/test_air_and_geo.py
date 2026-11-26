"""Unit and integration tests for data providers, demo mode, and air service."""

import json

import pytest
import respx
from httpx import AsyncClient, Response

from app.domain.models import LatLon, Scale
from app.main import app
from app.providers.demo import DemoProvider
from app.providers.nominatim import NominatimAdapter
from app.providers.open_meteo_air import OPEN_METEO_AIR_URL, OpenMeteoAirAdapter
from app.providers.open_meteo_weather import OPEN_METEO_FORECAST_URL, OpenMeteoWeatherAdapter
from app.providers.photon import CompositeGeocodeProvider, PhotonAdapter
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
async def test_open_meteo_adapters_respx() -> None:
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

    async with AsyncClient() as http_cli:
        air_adapter = OpenMeteoAirAdapter(http_cli)
        weather_adapter = OpenMeteoWeatherAdapter(http_cli)
        loc = LatLon(lat=28.6, lon=77.2)

        air_data = await air_adapter.get_air(loc)
        assert air_data["current"]["pm2_5"] == 85.0

        weather_data = await weather_adapter.get_weather(loc)
        assert weather_data["daily"]["sunrise"] == ["2026-11-25T06:30"]


@pytest.mark.asyncio
@respx.mock
async def test_nominatim_search_and_reverse() -> None:
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

    async with AsyncClient() as http_cli:
        nom = NominatimAdapter(http_cli)
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


@pytest.mark.asyncio
@respx.mock
async def test_photon_search_and_composite_fallback() -> None:
    photon_route = respx.get("https://photon.komoot.io/api/").mock(
        return_value=Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {"coordinates": [78.5011, 17.4337]},
                        "properties": {
                            "name": "Secunderabad Railway Station",
                            "district": "Secunderabad",
                            "city": "Hyderabad",
                            "state": "Telangana",
                            "country": "India",
                            "countrycode": "IN",
                            "osm_value": "station",
                        },
                    }
                ]
            },
        )
    )

    async with AsyncClient() as http_cli:
        photon = PhotonAdapter(http_cli)
        results = await photon.search("secundarabad railway station", lat=17.435, lon=78.427)
        assert len(results) == 1
        assert results[0]["name"] == "Secunderabad Railway Station"
        assert "Hyderabad" in results[0]["subtitle"]
        assert results[0]["country_code"] == "in"
        assert photon_route.called

    # Now test fallback to Nominatim when Photon fails
    respx.get("https://photon.komoot.io/api/").mock(return_value=Response(503))
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=Response(
            200,
            json=[
                {
                    "display_name": "Charminar, Hyderabad, Telangana, India",
                    "lat": "17.3616",
                    "lon": "78.4747",
                    "address": {"country_code": "in"},
                }
            ],
        )
    )
    async with AsyncClient() as http_cli:
        comp = CompositeGeocodeProvider(http_cli)
        fallback_results = await comp.search("Charminar Hyderabad")
        assert len(fallback_results) == 1
        assert "Charminar" in fallback_results[0]["label"]


@pytest.mark.asyncio
@respx.mock
async def test_geocode_endpoint_with_bias_and_photon(client: AsyncClient) -> None:
    respx.get("https://photon.komoot.io/api/").mock(
        return_value=Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {"coordinates": [78.5011, 17.4337]},
                        "properties": {
                            "name": "Secunderabad Junction",
                            "city": "Hyderabad",
                            "state": "Telangana",
                            "country": "India",
                            "countrycode": "IN",
                        },
                    }
                ]
            },
        )
    )
    prev_client = app.state.http_client
    async with AsyncClient() as real_http:
        app.state.http_client = real_http
        try:
            res = await client.get("/api/v1/geocode?q=secundarabad&lat=17.435&lon=78.427")
            assert res.status_code == 200
            data = res.json()["data"]
            assert len(data) == 1
            assert data[0]["name"] == "Secunderabad Junction"
        finally:
            app.state.http_client = prev_client


@pytest.mark.asyncio
@respx.mock
async def test_composite_geocode_ors_and_gemini_fallbacks() -> None:
    respx.get("https://photon.komoot.io/api/").mock(return_value=Response(503))
    ors_route = respx.get("https://api.openrouteservice.org/geocode/search").mock(
        return_value=Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {"coordinates": [77.2191, 28.6429]},
                        "properties": {
                            "name": "New Delhi Railway Station",
                            "locality": "New Delhi",
                            "region": "Delhi",
                            "country": "India",
                            "country_a": "IND",
                            "layer": "venue",
                        },
                    }
                ]
            },
        )
    )

    async with AsyncClient() as http_cli:
        comp_ors = CompositeGeocodeProvider(http_cli, ors_api_key="test-ors-key")
        ors_res = await comp_ors.search("New Delhi Railway Station")
        assert ors_route.called
        assert len(ors_res) == 1
        assert ors_res[0]["lat"] == 28.6429
        assert ors_res[0]["lon"] == 77.2191

    # Now test Gemini fallback when Photon + Nominatim return empty
    respx.get("https://photon.komoot.io/api/").mock(
        return_value=Response(200, json={"features": []})
    )
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=Response(200, json=[])
    )

    async def _fake_gemini_search(
        query: str, *, lat: float | None = None, lon: float | None = None
    ) -> list[dict[str, object]]:
        return [
            {
                "name": "Technopark Phase 1",
                "subtitle": "Thiruvananthapuram, Kerala, India",
                "label": "Technopark Phase 1, Thiruvananthapuram, Kerala, India",
                "lat": 8.5567,
                "lon": 76.8819,
                "country_code": "in",
                "category": "ai_resolved",
            }
        ]

    async with AsyncClient() as http_cli:
        comp_gem = CompositeGeocodeProvider(
            http_cli,
            gemini_api_key="test-gem-key",
            gemini_enabled=True,
        )
        assert comp_gem.gemini is not None
        comp_gem.gemini.search = _fake_gemini_search  # type: ignore[method-assign]
        gem_res = await comp_gem.search("Technopark Trivandrum")
        assert len(gem_res) == 1
        assert gem_res[0]["lat"] == 8.5567
        assert gem_res[0]["lon"] == 76.8819


@pytest.mark.asyncio
async def test_air_service_windows_json_serializable() -> None:
    demo = DemoProvider()
    svc = AirService(demo, demo)
    data = await svc.get_air(LatLon(lat=28.6315, lon=77.2167), scale=Scale.NAQI, is_demo=True)
    serialized = json.dumps(data)
    assert "cleanest" in serialized
