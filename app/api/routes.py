"""BreatheRoute comparison API endpoint."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.constants import ROUTE_COMPARE_PER_HOUR
from app.core.rate_limit import limiter
from app.core.security import get_client_ip, hash_subject, verify_same_origin
from app.dependencies import get_app_settings, get_http_client, get_store
from app.domain.models import LatLon, Mode, Scale, SensitiveGroup, SortOption
from app.providers.demo import DemoProvider
from app.providers.open_meteo_air import OpenMeteoAirAdapter
from app.providers.open_meteo_weather import OpenMeteoWeatherAdapter
from app.providers.ors import ORSAdapter
from app.providers.osrm import OSRMAdapter
from app.providers.overpass import OverpassAdapter
from app.providers.photon import CompositeGeocodeProvider
from app.services.route_service import RouteService

router = APIRouter(prefix="/api/v1", tags=["routes"])


class RouteCompareRequest(BaseModel):
    """Request schema for multi-mode route exposure comparison."""

    model_config = ConfigDict(extra="forbid")

    origin: LatLon | None = None
    origin_text: str | None = Field(default=None, min_length=2, max_length=250)
    destination: LatLon | None = None
    destination_text: str | None = Field(default=None, min_length=2, max_length=250)
    departure_time: datetime | None = None
    flexibility_minutes: int = Field(default=120, ge=0, le=180)
    modes: list[Mode] | None = None
    sort: SortOption = SortOption.LEAST_POLLUTION
    prefer_lit: bool = False
    sensitive: list[SensitiveGroup] = Field(default_factory=list)
    scale: Scale = Scale.NAQI


def get_route_service(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> tuple[RouteService, bool]:
    """Construct RouteService with live or demo providers."""
    is_demo = (
        request.headers.get("X-BreatheMap-Demo") in ("true", "1") or settings.DEMO_MODE == "force"
    )
    store = get_store(request)

    if is_demo:
        demo = DemoProvider()
        return (
            RouteService(
                air_provider=demo,
                weather_provider=demo,
                geo_provider=demo,
                primary_router=demo,
                fallback_router=None,
                lighting_provider=demo,
                cache_store=store,
                report_store=store,
            ),
            True,
        )

    client = get_http_client(request)
    ors_key = settings.ORS_API_KEY or ""
    osrm = OSRMAdapter(client)
    primary = ORSAdapter(client, ors_key) if ors_key else osrm
    fallback = osrm if ors_key else None

    geo_prov = CompositeGeocodeProvider(
        client,
        ors_api_key=settings.ORS_API_KEY,
        gemini_api_key=settings.GEMINI_API_KEY,
        gemini_model=settings.GEMINI_MODEL,
        gemini_enabled=settings.GEMINI_ENABLED,
    )

    return (
        RouteService(
            air_provider=OpenMeteoAirAdapter(client),
            weather_provider=OpenMeteoWeatherAdapter(client),
            geo_provider=geo_prov,
            primary_router=primary,
            fallback_router=fallback,
            lighting_provider=OverpassAdapter(client),
            cache_store=store,
            report_store=store,
        ),
        False,
    )


@router.post("/routes/compare")
async def compare_routes(
    body: RouteCompareRequest,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    service_bundle: tuple[RouteService, bool] = Depends(get_route_service),
) -> dict[str, Any]:
    """Compare travel modes and routes by estimated PM2.5 inhaled."""
    verify_same_origin(request, settings)
    ip = get_client_ip(request, is_production=settings.APP_ENV == "production")
    subject = hash_subject(ip, settings.APP_SECRET)
    limiter.check_and_record(f"route_compare:{subject}", ROUTE_COMPARE_PER_HOUR, 3600)

    service, is_demo = service_bundle
    result = await service.compare(
        origin_coord=body.origin,
        origin_text=body.origin_text,
        dest_coord=body.destination,
        dest_text=body.destination_text,
        departure_time=body.departure_time,
        flexibility_minutes=body.flexibility_minutes,
        modes=body.modes,
        sort_by=body.sort,
        prefer_lit=body.prefer_lit,
        is_demo=is_demo,
    )
    return {"data": result}
