"""Open-Meteo Weather Forecast API client adapter."""

from typing import Any

import httpx

from app.core.http import request_with_retry
from app.domain.models import LatLon
from app.providers.base import WeatherProvider

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoWeatherAdapter(WeatherProvider):
    """Adapter fetching weather and sunrise/sunset from Open-Meteo."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get_weather(self, location: LatLon) -> dict[str, Any]:
        params = {
            "latitude": round(location.lat, 4),
            "longitude": round(location.lon, 4),
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
            "daily": "sunrise,sunset",
            "timezone": "auto",
        }
        res = await request_with_retry(self.client, "GET", OPEN_METEO_FORECAST_URL, params=params)
        return res.json()  # type: ignore[no-any-return]
