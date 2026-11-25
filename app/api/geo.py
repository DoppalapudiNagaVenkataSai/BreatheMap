"""Geocoding, place search, and reverse geocoding endpoints."""

from typing import Any
from fastapi import APIRouter, Depends, Query, Request
from app.config import Settings
from app.dependencies import get_app_settings, get_http_client
from app.providers.demo import DemoProvider
from app.providers.nominatim import NominatimAdapter

router = APIRouter(prefix="/api/v1", tags=["geo"])


def get_geo_provider(request: Request, settings: Settings = Depends(get_app_settings)) -> Any:
    """Select between demo and Nominatim provider."""
    is_demo = request.headers.get("X-BreatheMap-Demo") == "true" or settings.DEMO_MODE == "force"
    if is_demo:
        return DemoProvider()
    client = get_http_client(request)
    return NominatimAdapter(client)


@router.get("/geocode")
async def geocode_query(
    q: str = Query(..., min_length=2, max_length=100),
    geo_provider: Any = Depends(get_geo_provider),
) -> dict[str, Any]:
    """Search forward geocode locations."""
    results = await geo_provider.search(q)
    return {"data": results}


@router.get("/reverse")
async def reverse_query(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    geo_provider: Any = Depends(get_geo_provider),
) -> dict[str, Any]:
    """Reverse geocode coordinate pair."""
    result = await geo_provider.reverse(lat, lon)
    return {"data": result}
