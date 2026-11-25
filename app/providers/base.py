"""Data provider protocols."""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.exposure import AirPoint
from app.domain.models import AirSnapshot, LatLon


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
