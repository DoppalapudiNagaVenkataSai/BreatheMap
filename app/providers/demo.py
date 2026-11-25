"""Demo provider loading static Delhi sample data."""

import json
from pathlib import Path
from typing import Any
from app.domain.models import LatLon
from app.providers.base import AirProvider, GeocodeProvider, WeatherProvider


class DemoProvider(AirProvider, WeatherProvider, GeocodeProvider):
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
