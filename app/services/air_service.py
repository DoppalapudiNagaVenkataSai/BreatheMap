"""Air service orchestrating parallel provider calls, domain calculations, and caching."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.constants import AIR_WEATHER_CACHE_TTL
from app.core.cache import get_or_set, make_cache_key
from app.domain.aqi import naqi, us_level
from app.domain.models import LatLon, Level, Scale
from app.domain.windows import cleanest_and_worst
from app.providers.base import AirProvider, WeatherProvider
from app.storage.base import CacheStore


class AirService:
    """Service that orchestrates air and weather data, AQI and windows."""

    def __init__(
        self,
        air_provider: AirProvider,
        weather_provider: WeatherProvider,
        cache_store: CacheStore | None = None,
    ) -> None:
        self.air_provider = air_provider
        self.weather_provider = weather_provider
        self.cache_store = cache_store

    async def get_air(
        self,
        location: LatLon,
        scale: Scale = Scale.NAQI,
        is_demo: bool = False,
    ) -> dict[str, Any]:
        """Fetch, calculate, and format air quality results with provenance."""
        cache_key = make_cache_key(
            "air",
            {
                "lat": round(location.lat, 2),
                "lon": round(location.lon, 2),
                "scale": scale.value,
                "is_demo": is_demo,
            },
        )

        async def _fetch_and_calculate() -> dict[str, Any]:
            air_raw, weather_raw = await asyncio.gather(
                self.air_provider.get_air(location),
                self.weather_provider.get_weather(location),
            )

            hourly_air = air_raw.get("hourly", {})
            current_air = air_raw.get("current", {})

            # Hourly times
            time_strs = hourly_air.get("time", [])
            times = [datetime.fromisoformat(t).replace(tzinfo=UTC) for t in time_strs]
            pm25_vals = hourly_air.get("pm2_5", [])

            # Compute Windows
            cleanest, worst = cleanest_and_worst(times, pm25_vals, window_h=3, horizon_h=24)

            # Current AQI computation
            current_pm25 = current_air.get("pm2_5")
            current_pm10 = current_air.get("pm10")
            current_no2 = current_air.get("nitrogen_dioxide")
            current_so2 = current_air.get("sulphur_dioxide")
            current_o3 = current_air.get("ozone")
            current_co = current_air.get("carbon_monoxide")
            if current_co is not None:
                current_co /= 1000.0  # µg/m³ to mg/m³

            aqi_res = naqi(
                {
                    "pm25": current_pm25,
                    "pm10": current_pm10,
                    "no2": current_no2,
                    "so2": current_so2,
                    "o3": current_o3,
                    "co": current_co,
                }
            )

            us_aqi_val = current_air.get("us_aqi")

            final_index = aqi_res.index if scale == Scale.NAQI else us_aqi_val
            final_level = (
                aqi_res.level
                if scale == Scale.NAQI
                else (us_level(us_aqi_val) if us_aqi_val else Level.L1)
            )

            # Weather context
            hourly_weather = weather_raw.get("hourly", {})
            current_temp = hourly_weather.get("temperature_2m", [None])[0]
            current_humidity = hourly_weather.get("relative_humidity_2m", [None])[0]
            current_wind = hourly_weather.get("wind_speed_10m", [None])[0]

            return {
                "location": {"lat": location.lat, "lon": location.lon},
                "scale": scale.value,
                "index": final_index,
                "level": final_level.value,
                "band": aqi_res.band,
                "dominant_pollutant": aqi_res.dominant,
                "pollutants": {
                    "pm25": current_pm25,
                    "pm10": current_pm10,
                    "no2": current_no2,
                    "so2": current_so2,
                    "o3": current_o3,
                    "co": current_co,
                },
                "weather": {
                    "temperature": current_temp,
                    "humidity": current_humidity,
                    "wind_speed": current_wind,
                },
                "windows": {
                    "cleanest": cleanest.model_dump() if cleanest else None,
                    "worst": worst.model_dump() if worst else None,
                },
                "hourly": {
                    "times": time_strs[:24],
                    "pm25": pm25_vals[:24],
                },
                "provenance": {
                    "source": "Open-Meteo modelled data" if not is_demo else "Delhi sample data",
                    "observed_at": datetime.now(tz=UTC).isoformat(),
                    "is_demo": is_demo,
                    "warnings": [
                        (
                            "Indicative NAQI, calculated from modelled data"
                            " — not an official CPCB station reading."
                        )
                    ]
                    if scale == Scale.NAQI
                    else [],
                },
            }

        return await get_or_set(
            self.cache_store, cache_key, AIR_WEATHER_CACHE_TTL, _fetch_and_calculate
        )
