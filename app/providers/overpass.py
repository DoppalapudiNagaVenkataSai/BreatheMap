"""Overpass API adapter for OpenStreetMap street lighting (lit) tags."""

from typing import Any

import httpx

from app.constants import OVERPASS_TIMEOUT
from app.core.errors import ProviderUnavailableError
from app.core.http import request_with_retry
from app.domain.geo import simplify_line
from app.providers.base import LightingProvider

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class OverpassAdapter(LightingProvider):
    """Adapter querying Overpass API for highway lit tags near a route."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get_lighting_ways(
        self, coordinates: list[tuple[float, float]]
    ) -> list[dict[str, Any]]:
        if len(coordinates) < 2:
            return []

        # Downsample to <= 60 points and round to 5 decimals for Overpass performance
        sampled = simplify_line(coordinates, max_points=60)
        coord_tokens = [f"{round(lat, 5)},{round(lon, 5)}" for lat, lon in sampled]
        around_list = ",".join(coord_tokens)

        query = (
            f"[out:json][timeout:{int(OVERPASS_TIMEOUT)}];"
            f"way[highway](around:25,{around_list});"
            "out tags geom;"
        )

        res = await request_with_retry(
            self.client,
            "POST",
            OVERPASS_URL,
            data={"data": query},
            timeout=OVERPASS_TIMEOUT,
        )
        if res.status_code == 429 or res.status_code >= 400:
            raise ProviderUnavailableError(f"Overpass lighting query failed ({res.status_code})")

        data = res.json()
        ways: list[dict[str, Any]] = []
        for elem in data.get("elements", []):
            if elem.get("type") != "way":
                continue
            geom = elem.get("geometry", [])
            coords = [
                (float(pt["lat"]), float(pt["lon"])) for pt in geom if "lat" in pt and "lon" in pt
            ]
            if len(coords) < 2:
                continue
            lit_tag = elem.get("tags", {}).get("lit", "unknown")
            ways.append({"lit": lit_tag, "coords": coords})

        return ways
