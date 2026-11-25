"""FOSSGIS OSRM fallback routing client adapter."""

import httpx

from app.core.errors import ProviderUnavailableError
from app.core.http import request_with_retry
from app.domain.models import LatLon, Mode, RouteGeometry
from app.providers.base import RawRoute, RoutingProvider

OSRM_BASE_URL = "https://routing.openstreetmap.de"

OSRM_SERVICE_MAP: dict[Mode, tuple[str, str]] = {
    Mode.WALK: ("routed-foot", "foot"),
    Mode.CYCLE: ("routed-bike", "bike"),
    Mode.CAR: ("routed-car", "car"),
}


class OSRMAdapter(RoutingProvider):
    """Fallback routing adapter using FOSSGIS OSRM."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get_routes(self, origin: LatLon, destination: LatLon, mode: Mode) -> list[RawRoute]:
        mapping = OSRM_SERVICE_MAP.get(mode)
        if not mapping:
            return []

        service, profile = mapping
        coords_str = f"{origin.lon},{origin.lat};{destination.lon},{destination.lat}"
        url = f"{OSRM_BASE_URL}/{service}/route/v1/{profile}/{coords_str}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "alternatives": "true",
        }

        res = await request_with_retry(self.client, "GET", url, params=params)
        if res.status_code == 429 or res.status_code >= 400:
            raise ProviderUnavailableError(f"OSRM routing failed ({res.status_code})")

        data = res.json()
        if data.get("code") != "Ok":
            return []

        routes: list[RawRoute] = []
        for r in data.get("routes", [])[:3]:
            raw_coords = r.get("geometry", {}).get("coordinates", [])
            coords = [(float(pt[1]), float(pt[0])) for pt in raw_coords if len(pt) >= 2]
            if len(coords) < 2:
                continue

            routes.append(
                RawRoute(
                    distance_m=float(r.get("distance", 0.0)),
                    duration_s=float(r.get("duration", 0.0)),
                    geometry=RouteGeometry(coordinates=coords, waytypes=None),
                )
            )

        return routes
