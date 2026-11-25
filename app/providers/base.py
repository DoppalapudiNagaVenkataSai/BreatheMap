"""Data provider protocols."""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.domain.models import LatLon, Mode, RouteGeometry


@dataclass
class RawRoute:
    """Internal route representation returned by routing providers."""

    distance_m: float
    duration_s: float
    geometry: RouteGeometry


@runtime_checkable
class AirProvider(Protocol):
    """Protocol for fetching hourly and current atmospheric pollutant series."""

    async def get_air(self, location: LatLon) -> dict[str, Any]:
        """Fetch modelled air data."""
        ...


@runtime_checkable
class WeatherProvider(Protocol):
    """Protocol for weather parameters, sunrise, and sunset."""

    async def get_weather(self, location: LatLon) -> dict[str, Any]:
        """Fetch forecast weather data."""
        ...


@runtime_checkable
class GeocodeProvider(Protocol):
    """Protocol for forward and reverse geocoding."""

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search places by query."""
        ...

    async def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Reverse geocode coordinates into label."""
        ...


@runtime_checkable
class RoutingProvider(Protocol):
    """Protocol for fetching candidate routes for walk, cycle, or car."""

    async def get_routes(self, origin: LatLon, destination: LatLon, mode: Mode) -> list[RawRoute]:
        """Fetch 1-3 candidate routes for the specified mode."""
        ...


@runtime_checkable
class LightingProvider(Protocol):
    """Protocol for fetching street lighting tags along a route."""

    async def get_lighting_ways(
        self, coordinates: list[tuple[float, float]]
    ) -> list[dict[str, Any]]:
        """Fetch OSM highway ways with lit tags near coordinates."""
        ...
