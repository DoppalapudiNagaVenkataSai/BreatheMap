"""Air quality information endpoint."""

from typing import Any
from fastapi import APIRouter, Depends, Query, Request
from app.config import Settings
from app.dependencies import get_app_settings, get_http_client, get_store
from app.domain.models import LatLon, Scale
from app.providers.demo import DemoProvider
from app.providers.open_meteo_air import OpenMeteoAirAdapter
from app.providers.open_meteo_weather import OpenMeteoWeatherAdapter
from app.services.air_service import AirService

router = APIRouter(prefix="/api/v1", tags=["air"])


def get_air_service(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> tuple[AirService, bool]:
    """Construct AirService with appropriate live or demo provider."""
    is_demo = request.headers.get("X-BreatheMap-Demo") == "true" or settings.DEMO_MODE == "force"
    store = get_store(request)

    if is_demo:
        demo = DemoProvider()
        return AirService(demo, demo, cache_store=store), True

    client = get_http_client(request)
    air_p = OpenMeteoAirAdapter(client)
    weather_p = OpenMeteoWeatherAdapter(client)
    return AirService(air_p, weather_p, cache_store=store), False


@router.get("/air")
async def get_air_data(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    scale: Scale = Query(Scale.NAQI),
    service_bundle: tuple[AirService, bool] = Depends(get_air_service),
) -> dict[str, Any]:
    """Get calculated AQI, pollutant breakdown, windows, and weather context."""
    service, is_demo = service_bundle
    loc = LatLon(lat=lat, lon=lon)
    result = await service.get_air(loc, scale=scale, is_demo=is_demo)
    return {"data": result}
