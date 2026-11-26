"""Komoot Photon, ORS Pelias, Nominatim, and optional Gemini geocoding providers."""

import asyncio
from typing import Any

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel

from app.constants import GEOCODE_CACHE_TTL
from app.core.cache import l1_cache, make_cache_key
from app.core.errors import ProviderUnavailableError
from app.core.http import request_with_retry
from app.providers.base import GeocodeProvider
from app.providers.nominatim import NominatimAdapter

PHOTON_SEARCH_URL = "https://photon.komoot.io/api/"
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"
ORS_GEOCODE_SEARCH_URL = "https://api.openrouteservice.org/geocode/search"
ORS_GEOCODE_REVERSE_URL = "https://api.openrouteservice.org/geocode/reverse"
GEMINI_GEOCODE_TIMEOUT = 8.0


class _GeminiPlace(BaseModel):
    name: str
    subtitle: str = ""
    lat: float
    lon: float
    country_code: str = "in"


class _GeminiGeocodeResponse(BaseModel):
    places: list[_GeminiPlace]


def _format_pelias_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    """Convert an ORS Pelias GeoJSON feature into a normalized place dict."""
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    lon = float(coords[0])
    lat = float(coords[1])
    props = feature.get("properties") or {}
    name = str(props.get("name") or props.get("label") or "").strip()
    if not name:
        return None
    parts = [
        props.get("locality") or props.get("localadmin") or "",
        props.get("region") or "",
        props.get("country") or "",
    ]
    seen: set[str] = {name.lower()}
    sub_parts: list[str] = []
    for part in parts:
        cleaned = str(part).strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            sub_parts.append(cleaned)
    subtitle = ", ".join(sub_parts)
    label = str(props.get("label") or (f"{name}, {subtitle}" if subtitle else name))
    return {
        "name": name,
        "subtitle": subtitle,
        "label": label,
        "lat": lat,
        "lon": lon,
        "country_code": str(props.get("country_a") or "in")[:2].lower(),
        "category": str(props.get("layer") or ""),
    }


class ORSGeocodeAdapter(GeocodeProvider):
    """OpenRouteService Pelias geocoding adapter using ORS_API_KEY."""

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    async def search(
        self, query: str, *, lat: float | None = None, lon: float | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"api_key": self.api_key, "text": query, "size": 6}
        if lat is not None and lon is not None:
            params["focus.point.lat"] = round(lat, 4)
            params["focus.point.lon"] = round(lon, 4)
        res = await request_with_retry(self.client, "GET", ORS_GEOCODE_SEARCH_URL, params=params)
        if res.status_code >= 400:
            raise ProviderUnavailableError(f"ORS geocode returned HTTP {res.status_code}")
        results: list[dict[str, Any]] = []
        for feature in res.json().get("features", []):
            item = _format_pelias_feature(feature)
            if item is not None:
                results.append(item)
        return results

    async def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        res = await request_with_retry(
            self.client,
            "GET",
            ORS_GEOCODE_REVERSE_URL,
            params={"api_key": self.api_key, "point.lat": lat, "point.lon": lon, "size": 1},
        )
        if res.status_code >= 400:
            raise ProviderUnavailableError(f"ORS reverse returned HTTP {res.status_code}")
        features = res.json().get("features", [])
        if not features:
            return None
        formatted = _format_pelias_feature(features[0])
        if formatted is not None:
            formatted["lat"] = lat
            formatted["lon"] = lon
        return formatted


class GeminiGeocodeAdapter:
    """Fallback geocoder using Gemini API key to resolve place details to lat/lon."""

    def __init__(self, api_key: str, model: str = "gemini-3.8-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def search(
        self, query: str, *, lat: float | None = None, lon: float | None = None
    ) -> list[dict[str, Any]]:
        bias_hint = (
            f" Bias toward coordinates near ({lat:.4f}, {lon:.4f}) if ambiguous."
            if lat is not None and lon is not None
            else ""
        )
        prompt = (
            f"Convert the location query into up to 3 real geographic places with accurate WGS84 "
            f"latitude and longitude.{bias_hint} If the query is not a real place, return an "
            f"empty places list.\nQuery: {query.strip()}"
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_GeminiGeocodeResponse,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            max_output_tokens=512,
        )
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                ),
                timeout=GEMINI_GEOCODE_TIMEOUT,
            )
            parsed = _GeminiGeocodeResponse.model_validate_json(response.text or "")
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        for p in parsed.places[:3]:
            if not (-90.0 <= p.lat <= 90.0 and -180.0 <= p.lon <= 180.0):
                continue
            if p.lat == 0.0 and p.lon == 0.0:
                continue
            name = p.name.strip()
            if not name:
                continue
            subtitle = p.subtitle.strip()
            results.append(
                {
                    "name": name,
                    "subtitle": subtitle,
                    "label": f"{name}, {subtitle}" if subtitle else name,
                    "lat": round(p.lat, 6),
                    "lon": round(p.lon, 6),
                    "country_code": (p.country_code or "in")[:2].lower(),
                    "category": "ai_resolved",
                }
            )
        return results


def _format_photon_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a Photon GeoJSON feature into a normalized place dict."""
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    lon = float(coords[0])
    lat = float(coords[1])
    props = feature.get("properties") or {}

    street = props.get("street") or ""
    housenumber = props.get("housenumber") or ""
    street_part = f"{housenumber} {street}".strip() if street else ""

    name = (
        props.get("name")
        or street_part
        or props.get("district")
        or props.get("locality")
        or props.get("city")
        or props.get("county")
        or ""
    )
    if not name:
        return None

    subtitle_candidates = [
        street_part if street_part != name else "",
        props.get("district") or props.get("locality") or "",
        props.get("city") or props.get("town") or props.get("village") or props.get("county") or "",
        props.get("state") or "",
        props.get("country") or "",
    ]
    seen: set[str] = {name.lower()}
    subtitle_parts: list[str] = []
    for part in subtitle_candidates:
        cleaned = str(part).strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            subtitle_parts.append(cleaned)

    subtitle = ", ".join(subtitle_parts)
    label = f"{name}, {subtitle}" if subtitle else name

    return {
        "name": name,
        "subtitle": subtitle,
        "label": label,
        "lat": lat,
        "lon": lon,
        "country_code": str(props.get("countrycode") or "in").lower(),
        "category": str(props.get("osm_value") or props.get("type") or ""),
    }


class PhotonAdapter(GeocodeProvider):
    """Fast, typo-tolerant OSM geocoding via Komoot Photon."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def search(
        self, query: str, *, lat: float | None = None, lon: float | None = None
    ) -> list[dict[str, Any]]:
        """Forward geocode with optional location bias for Google Maps-like ranking."""
        params: dict[str, Any] = {"q": query, "limit": 6, "lang": "en"}
        if lat is not None and lon is not None:
            params["lat"] = round(lat, 4)
            params["lon"] = round(lon, 4)

        res = await request_with_retry(self.client, "GET", PHOTON_SEARCH_URL, params=params)
        if res.status_code >= 400:
            raise ProviderUnavailableError(f"Photon returned HTTP {res.status_code}")

        payload = res.json()
        results: list[dict[str, Any]] = []
        seen_keys: set[tuple[float, float, str]] = set()
        for feature in payload.get("features", []):
            item = _format_photon_feature(feature)
            if item is None:
                continue
            dedup_key = (round(item["lat"], 4), round(item["lon"], 4), item["label"].lower())
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            results.append(item)
        return results

    async def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Reverse geocode coordinates using Photon."""
        res = await request_with_retry(
            self.client,
            "GET",
            PHOTON_REVERSE_URL,
            params={"lat": lat, "lon": lon, "lang": "en"},
        )
        if res.status_code >= 400:
            raise ProviderUnavailableError(f"Photon reverse failed ({res.status_code})")
        features = res.json().get("features", [])
        if not features:
            return None
        formatted = _format_photon_feature(features[0])
        if formatted is None:
            return None
        formatted["lat"] = lat
        formatted["lon"] = lon
        return formatted


class CompositeGeocodeProvider(GeocodeProvider):
    """Cached geocoding: Photon -> ORS (if key) -> Nominatim/Open-Meteo -> Gemini (if enabled)."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        ors_api_key: str | None = None,
        gemini_api_key: str | None = None,
        gemini_model: str = "gemini-3.8-flash",
        gemini_enabled: bool = False,
    ) -> None:
        self.photon = PhotonAdapter(client)
        self.nominatim = NominatimAdapter(client)
        self.ors = ORSGeocodeAdapter(client, ors_api_key) if ors_api_key else None
        self.gemini = (
            GeminiGeocodeAdapter(gemini_api_key, model=gemini_model)
            if gemini_enabled and gemini_api_key
            else None
        )

    async def _try_search(
        self, query: str, *, lat: float | None = None, lon: float | None = None
    ) -> list[dict[str, Any]]:
        try:
            results = await self.photon.search(query, lat=lat, lon=lon)
            if results:
                return results
        except (ProviderUnavailableError, httpx.HTTPError):
            pass

        if self.ors is not None:
            try:
                results = await self.ors.search(query, lat=lat, lon=lon)
                if results:
                    return results
            except (ProviderUnavailableError, httpx.HTTPError):
                pass

        try:
            results = await self.nominatim.search(query)
            if results:
                return results
        except (ProviderUnavailableError, httpx.HTTPError):
            pass

        if self.gemini is not None:
            return await self.gemini.search(query, lat=lat, lon=lon)
        return []

    async def search(
        self, query: str, *, lat: float | None = None, lon: float | None = None
    ) -> list[dict[str, Any]]:
        """Search places with L1 cache and multi-provider fallback including API-key geocoders."""
        normalized = " ".join(query.strip().lower().split())
        cache_payload: dict[str, Any] = {"q": normalized}
        if lat is not None and lon is not None:
            cache_payload["lat"] = round(lat, 2)
            cache_payload["lon"] = round(lon, 2)
        cache_key = make_cache_key("geocode", cache_payload)

        cached = l1_cache.get(cache_key)
        if isinstance(cached, list):
            return cached

        results = await self._try_search(query, lat=lat, lon=lon)
        if results:
            l1_cache.set(cache_key, results, GEOCODE_CACHE_TTL)
        return results

    async def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Reverse geocode with Nominatim primary, Photon fallback, and ORS fallback."""
        try:
            res = await self.nominatim.reverse(lat, lon)
            if res is not None:
                return res
        except (ProviderUnavailableError, httpx.HTTPError):
            pass

        try:
            res = await self.photon.reverse(lat, lon)
            if res is not None:
                return res
        except (ProviderUnavailableError, httpx.HTTPError):
            pass

        if self.ors is not None:
            try:
                return await self.ors.reverse(lat, lon)
            except (ProviderUnavailableError, httpx.HTTPError):
                return None
        return None
