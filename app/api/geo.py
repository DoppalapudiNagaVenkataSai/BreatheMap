"""Geocoding, place search, and reverse geocoding endpoints."""

import re
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.config import Settings
from app.dependencies import get_app_settings, get_http_client
from app.providers.demo import DemoProvider
from app.providers.nominatim import NominatimAdapter

router = APIRouter(prefix="/api/v1", tags=["geo"])
_COORD_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$")


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
    """Search forward geocode locations (or parse direct 'lat, lon' coordinates)."""
    coord_match = _COORD_RE.match(q)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return {
                "data": [
                    {
                        "label": f"{lat:.4f}, {lon:.4f}",
                        "lat": lat,
                        "lon": lon,
                        "country_code": "in",
                    }
                ]
            }
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
