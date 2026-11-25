"""OpenStreetMap Nominatim geocoding client adapter with rate limiting."""

import asyncio
import time
from typing import Any

import httpx

from app.core.errors import ProviderUnavailableError
from app.core.http import request_with_retry
from app.providers.base import GeocodeProvider

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class NominatimAdapter(GeocodeProvider):
    """Adapter for Nominatim geocoding enforcing 1 req/sec lock."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self._lock = asyncio.Lock()
        self._last_call_time = 0.0

    async def _rate_limit(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_call_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            self._last_call_time = time.monotonic()

    async def _fallback_open_meteo_search(self, query: str) -> list[dict[str, Any]]:
        """Fallback to Open-Meteo Geocoding API if Nominatim blocks/rate-limits."""
        res = await request_with_retry(
            self.client,
            "GET",
            OPEN_METEO_GEOCODE_URL,
            params={"name": query, "count": 5, "language": "en", "format": "json"},
        )
        if res.status_code >= 400:
            raise ProviderUnavailableError(f"Geocoding fallback failed ({res.status_code})")
        payload = res.json()
        results: list[dict[str, Any]] = []
        for item in payload.get("results", []):
            parts = [item.get("name"), item.get("admin1"), item.get("country")]
            label = ", ".join(str(p) for p in parts if p)
            results.append(
                {
                    "label": label or query,
                    "lat": float(item["latitude"]),
                    "lon": float(item["longitude"]),
                    "country_code": str(item.get("country_code", "in")).lower(),
                }
            )
        return results

    async def search(self, query: str) -> list[dict[str, Any]]:
        await self._rate_limit()
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "addressdetails": 1,
        }
        try:
            res = await request_with_retry(self.client, "GET", NOMINATIM_SEARCH_URL, params=params)
            if res.status_code >= 400:
                return await self._fallback_open_meteo_search(query)
            data = res.json()
        except ProviderUnavailableError:
            return await self._fallback_open_meteo_search(query)

        results: list[dict[str, Any]] = []
        for item in data:
            addr = item.get("address", {})
            results.append(
                {
                    "label": item.get("display_name", ""),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "country_code": addr.get("country_code", "in").lower(),
                }
            )
        return results

    async def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        await self._rate_limit()
        params = {
            "lat": lat,
            "lon": lon,
            "format": "jsonv2",
            "addressdetails": 1,
        }
        res = await request_with_retry(self.client, "GET", NOMINATIM_REVERSE_URL, params=params)
        if res.status_code >= 400:
            raise ProviderUnavailableError(f"Nominatim reverse failed ({res.status_code})")
        item = res.json()
        if "error" in item:
            return None
        addr = item.get("address", {})
        return {
            "label": item.get("display_name", ""),
            "lat": lat,
            "lon": lon,
            "country_code": addr.get("country_code", "in").lower(),
        }
