"""Demo provider loading static Delhi sample data."""

import json
from pathlib import Path
from typing import Any

from app.domain.geo import haversine_m
from app.domain.models import LatLon, Mode, RouteGeometry
from app.providers.base import (
    AirProvider,
    GeocodeProvider,
    LightingProvider,
    RawRoute,
    RoutingProvider,
    WeatherProvider,
)


class DemoProvider(
    AirProvider, WeatherProvider, GeocodeProvider, RoutingProvider, LightingProvider
):
    """Provides canned Delhi sample data offline."""

    def __init__(self, data_dir: Path | str = "data/demo") -> None:
        self.data_dir = Path(data_dir)

    async def get_air(self, location: LatLon) -> dict[str, Any]:
        p = self.data_dir / "delhi_air.json"
        with open(p, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    async def get_weather(self, location: LatLon) -> dict[str, Any]:
        p = self.data_dir / "delhi_weather.json"
        with open(p, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    async def search(self, query: str) -> list[dict[str, Any]]:
        p = self.data_dir / "delhi_places.json"
        with open(p, encoding="utf-8") as f:
            places: list[dict[str, Any]] = json.load(f)
        q = query.lower()
        matched = [place for place in places if q in place["label"].lower()]
        return matched or places[:3]

    async def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        p = self.data_dir / "delhi_places.json"
        with open(p, encoding="utf-8") as f:
            places: list[dict[str, Any]] = json.load(f)
        return places[0]

    async def get_routes(self, origin: LatLon, destination: LatLon, mode: Mode) -> list[RawRoute]:
        p = self.data_dir / "delhi_routes.json"
        with open(p, encoding="utf-8") as f:
            data = json.load(f)

        trips = data.get("trips", [])
        best_trip = None
        best_dist = float("inf")
        for trip in trips:
            t_orig = trip["origin"]
            t_dest = trip["destination"]
            d = haversine_m(origin.lat, origin.lon, t_orig[0], t_orig[1]) + haversine_m(
                destination.lat, destination.lon, t_dest[0], t_dest[1]
            )
            if d < best_dist:
                best_dist = d
                best_trip = trip

        # If close to a canned trip (< 3 km combined), return its canned routes
        if best_trip and best_dist < 3000.0:
            raw_list = best_trip.get("modes", {}).get(mode.value, [])
            if raw_list:
                return [
                    RawRoute(
                        distance_m=float(item["distance_m"]),
                        duration_s=float(item["duration_s"]),
                        geometry=RouteGeometry(
                            coordinates=[(pt[0], pt[1]) for pt in item["coordinates"]],
                            waytypes=item.get("waytypes"),
                        ),
                    )
                    for item in raw_list
                ]

        # Otherwise generate a clean synthetic 2-point fallback for arbitrary demo points
        dist_m = max(150.0, haversine_m(origin.lat, origin.lon, destination.lat, destination.lon))
        speed_mps = {Mode.WALK: 1.35, Mode.CYCLE: 4.2, Mode.CAR: 7.5}.get(mode, 5.0)
        mid = ((origin.lat + destination.lat) / 2.0, (origin.lon + destination.lon) / 2.0)
        return [
            RawRoute(
                distance_m=round(dist_m * 1.2, 1),
                duration_s=round((dist_m * 1.2) / speed_mps, 1),
                geometry=RouteGeometry(
                    coordinates=[(origin.lat, origin.lon), mid, (destination.lat, destination.lon)],
                    waytypes=["street", "street"],
                ),
            )
        ]

    async def get_lighting_ways(
        self, coordinates: list[tuple[float, float]]
    ) -> list[dict[str, Any]]:
        p = self.data_dir / "delhi_lighting.json"
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("ways", [])  # type: ignore[no-any-return]
