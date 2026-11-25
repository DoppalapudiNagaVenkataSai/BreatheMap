"""openrouteservice Directions v2 API client adapter."""

from typing import Any

import httpx

from app.core.errors import ProviderUnavailableError
from app.core.http import request_with_retry
from app.domain.geo import haversine_m
from app.domain.models import LatLon, Mode, RouteGeometry
from app.providers.base import RawRoute, RoutingProvider

ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions"

ORS_PROFILE_MAP: dict[Mode, str] = {
    Mode.WALK: "foot-walking",
    Mode.CYCLE: "cycling-regular",
    Mode.CAR: "driving-car",
}

ORS_WAYTYPE_MAP: dict[int, str] = {
    0: "unknown",
    1: "state",
    2: "major",
    3: "street",
    4: "path",
    5: "track",
    6: "cycleway",
    7: "footway",
    8: "steps",
    9: "ferry",
    10: "construction",
}


def _map_waytypes(num_coords: int, waytype_values: list[list[int]] | None) -> list[str] | None:
    """Map ORS waytype index ranges [start_idx, end_idx, type_id] to per-segment labels."""
    if not waytype_values or num_coords < 2:
        return None
    seg_types = ["unknown"] * (num_coords - 1)
    for start_idx, end_idx, type_id in waytype_values:
        label = ORS_WAYTYPE_MAP.get(type_id, "unknown")
        for idx in range(max(0, start_idx), min(num_coords - 1, end_idx)):
            seg_types[idx] = label
    return seg_types


class ORSAdapter(RoutingProvider):
    """Primary routing adapter using openrouteservice Directions v2."""

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    async def get_routes(self, origin: LatLon, destination: LatLon, mode: Mode) -> list[RawRoute]:
        if not self.api_key:
            raise ProviderUnavailableError("ORS API key is not configured")

        profile = ORS_PROFILE_MAP.get(mode)
        if not profile:
            return []

        url = f"{ORS_BASE_URL}/{profile}/geojson"
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json; charset=utf-8",
        }

        dist_m = haversine_m(origin.lat, origin.lon, destination.lat, destination.lon)
        payload: dict[str, Any] = {
            "coordinates": [
                [origin.lon, origin.lat],
                [destination.lon, destination.lat],
            ],
            "extra_info": ["waytype"],
        }
        if 500.0 <= dist_m < 100000.0:
            payload["alternative_routes"] = {
                "target_count": 3,
                "weight_factor": 1.4,
                "share_factor": 0.6,
            }

        res = await request_with_retry(self.client, "POST", url, headers=headers, json_body=payload)
        if res.status_code == 429:
            raise ProviderUnavailableError("ORS quota exceeded (429)")
        if res.status_code >= 400:
            # If alternative_routes caused a 400 on a short/edge route, retry once without it
            if "alternative_routes" in payload and res.status_code == 400:
                payload.pop("alternative_routes")
                res = await request_with_retry(
                    self.client, "POST", url, headers=headers, json_body=payload
                )
            if res.status_code >= 400:
                raise ProviderUnavailableError(f"ORS routing failed ({res.status_code})")

        data = res.json()
        features = data.get("features", [])
        routes: list[RawRoute] = []

        for feat in features[:3]:
            geom = feat.get("geometry", {})
            raw_coords = geom.get("coordinates", [])
            # Convert [lon, lat] -> (lat, lon)
            coords = [(float(pt[1]), float(pt[0])) for pt in raw_coords if len(pt) >= 2]
            if len(coords) < 2:
                continue

            props = feat.get("properties", {})
            summary = props.get("summary", {})
            distance_m = float(summary.get("distance", 0.0))
            duration_s = float(summary.get("duration", 0.0))

            waytype_values = props.get("extras", {}).get("waytype", {}).get("values")
            waytypes = _map_waytypes(len(coords), waytype_values)

            routes.append(
                RawRoute(
                    distance_m=distance_m,
                    duration_s=duration_s,
                    geometry=RouteGeometry(coordinates=coords, waytypes=waytypes),
                )
            )

        return routes
