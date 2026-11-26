"""AI Assistant chat endpoint (Section 13)."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.assistant.gemini_client import FakeGeminiClient, GeminiClient, RealGeminiClient
from app.config import Settings
from app.constants import API_RATE_LIMIT_PER_MINUTE
from app.core.rate_limit import limiter
from app.core.security import get_client_ip, hash_subject, verify_same_origin
from app.dependencies import get_app_settings, get_http_client, get_store
from app.providers.demo import DemoProvider
from app.providers.open_meteo_air import OpenMeteoAirAdapter
from app.providers.open_meteo_weather import OpenMeteoWeatherAdapter
from app.providers.ors import ORSAdapter
from app.providers.osrm import OSRMAdapter
from app.providers.overpass import OverpassAdapter
from app.providers.photon import CompositeGeocodeProvider
from app.services.air_service import AirService
from app.services.assistant_service import AssistantService
from app.services.report_service import ReportService
from app.services.route_service import RouteService

router = APIRouter(prefix="/api/v1", tags=["assistant"])


class AssistantChatRequest(BaseModel):
    """Request schema for POST /api/v1/assistant/chat."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=500)
    context: dict[str, Any] = Field(default_factory=dict)
    recent_turns: list[str] = Field(default_factory=list, max_length=2)


def get_gemini_client(settings: Settings = Depends(get_app_settings)) -> GeminiClient:
    """Provide RealGeminiClient when enabled with key, else offline FakeGeminiClient."""
    if settings.GEMINI_ENABLED and settings.GEMINI_API_KEY:
        return RealGeminiClient(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
    return FakeGeminiClient()


def get_assistant_service(
    request: Request,
    settings: Settings = Depends(get_app_settings),
    gemini_client: GeminiClient = Depends(get_gemini_client),
) -> tuple[AssistantService, bool]:
    """Construct AssistantService wired with live or demo deterministic providers."""
    is_demo = (
        request.headers.get("X-BreatheMap-Demo") in ("true", "1") or settings.DEMO_MODE == "force"
    )
    store = get_store(request)

    if is_demo:
        demo = DemoProvider()
        air_svc = AirService(demo, demo, cache_store=store)
        route_svc = RouteService(
            air_provider=demo,
            weather_provider=demo,
            geo_provider=demo,
            primary_router=demo,
            fallback_router=None,
            lighting_provider=demo,
            cache_store=store,
            report_store=store,
        )
        geo_prov: Any = demo
    else:
        client = get_http_client(request)
        air_svc = AirService(
            OpenMeteoAirAdapter(client), OpenMeteoWeatherAdapter(client), cache_store=store
        )
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
        route_svc = RouteService(
            air_provider=OpenMeteoAirAdapter(client),
            weather_provider=OpenMeteoWeatherAdapter(client),
            geo_provider=geo_prov,
            primary_router=primary,
            fallback_router=fallback,
            lighting_provider=OverpassAdapter(client),
            cache_store=store,
            report_store=store,
        )

    service = AssistantService(
        settings=settings,
        store=store,
        air_service=air_svc,
        route_service=route_svc,
        report_service=ReportService(store),
        geo_provider=geo_prov,
        gemini_client=gemini_client,
    )
    return service, is_demo


@router.post("/assistant/chat")
async def assistant_chat(
    body: AssistantChatRequest,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    service_bundle: tuple[AssistantService, bool] = Depends(get_assistant_service),
) -> dict[str, Any]:
    """Handle natural-language air-exposure chat using deterministic tools and optional Gemini."""
    verify_same_origin(request, settings)
    ip = get_client_ip(request, is_production=settings.APP_ENV == "production")
    reporter_hash = hash_subject(ip, settings.APP_SECRET)
    limiter.check_and_record(f"api:{reporter_hash}", API_RATE_LIMIT_PER_MINUTE, 60)

    service, is_demo = service_bundle
    data, cached = await service.chat(
        message=body.message,
        context=body.context,
        recent_turns=body.recent_turns,
        reporter_hash=reporter_hash,
        is_demo=is_demo,
    )
    now_iso = datetime.now(UTC).isoformat()
    return {
        "data": data,
        "meta": {
            "source": [data["provenance"]["source"]],
            "observed_at": now_iso,
            "fetched_at": now_iso,
            "is_demo": is_demo,
            "cached": cached,
            "warnings": [],
        },
    }
