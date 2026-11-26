"""Geocoding, place search, and reverse geocoding endpoints."""

import re
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.config import Settings
from app.dependencies import get_app_settings, get_http_client
from app.providers.demo import DemoProvider
from app.providers.photon import CompositeGeocodeProvider

router = APIRouter(prefix="/api/v1", tags=["geo"])
_COORD_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$")


def get_geo_provider(request: Request, settings: Settings = Depends(get_app_settings)) -> Any:
    """Select between demo and live composite geocoding provider."""
    is_demo = request.headers.get("X-BreatheMap-Demo") == "true" or settings.DEMO_MODE == "force"
    if is_demo:
        return DemoProvider()
    client = get_http_client(request)
    return CompositeGeocodeProvider(
        client,
        ors_api_key=settings.ORS_API_KEY,
        gemini_api_key=settings.GEMINI_API_KEY,
        gemini_model=settings.GEMINI_MODEL,
        gemini_enabled=settings.GEMINI_ENABLED,
    )


@router.get("/geocode")
async def geocode_query(
    q: str = Query(..., min_length=2, max_length=250),
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    geo_provider: Any = Depends(get_geo_provider),
) -> dict[str, Any]:
    """Search forward geocode locations (or parse direct 'lat, lon' coordinates)."""
    coord_match = _COORD_RE.match(q)
    if coord_match:
        coord_lat = float(coord_match.group(1))
        coord_lon = float(coord_match.group(2))
        if -90.0 <= coord_lat <= 90.0 and -180.0 <= coord_lon <= 180.0:
            return {
                "data": [
                    {
                        "name": f"{coord_lat:.4f}, {coord_lon:.4f}",
                        "subtitle": "Coordinates",
                        "label": f"{coord_lat:.4f}, {coord_lon:.4f}",
                        "lat": coord_lat,
                        "lon": coord_lon,
                        "country_code": "in",
                    }
                ]
            }
    if isinstance(geo_provider, CompositeGeocodeProvider):
        results = await geo_provider.search(q, lat=lat, lon=lon)
    else:
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
