"""Open-Meteo Air Quality API client adapter."""

from typing import Any

import httpx

from app.core.http import request_with_retry
from app.domain.models import LatLon
from app.providers.base import AirProvider

OPEN_METEO_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


class OpenMeteoAirAdapter(AirProvider):
    """Adapter fetching air quality from Open-Meteo."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get_air(self, location: LatLon) -> dict[str, Any]:
        params = {
            "latitude": round(location.lat, 4),
            "longitude": round(location.lon, 4),
            "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi",
            "current": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi",
            "past_days": 1,
            "forecast_days": 2,
            "timezone": "auto",
        }
        res = await request_with_retry(self.client, "GET", OPEN_METEO_AIR_URL, params=params)
        return res.json()  # type: ignore[no-any-return]
