#!/usr/bin/env python3
"""Helper script for the owner to re-record live Delhi demo fixtures using real API keys."""

import asyncio
import json
from pathlib import Path

from app.config import get_settings
from app.core.http import create_http_client
from app.domain.geo import simplify_line
from app.domain.models import LatLon, Mode
from app.providers.ors import ORSAdapter
from app.providers.overpass import OverpassAdapter

TRIPS = [
    ("Connaught Place to New Delhi Railway Station", (28.6315, 77.2167), (28.6430, 77.2194)),
    ("Lodhi Garden to India Gate", (28.5931, 77.2197), (28.6129, 77.2295)),
]


async def main() -> None:
    settings = get_settings()
    if not settings.ORS_API_KEY:
        print("ORS_API_KEY must be set in .env to record live route fixtures.")
        return

    async with create_http_client(settings.NOMINATIM_CONTACT_EMAIL) as client:
        ors = ORSAdapter(client, settings.ORS_API_KEY)
        overpass = OverpassAdapter(client)

        recorded_trips = []
        all_lighting_ways = []

        for name, orig, dest in TRIPS:
            o_loc = LatLon(lat=orig[0], lon=orig[1])
            d_loc = LatLon(lat=dest[0], lon=dest[1])
            modes_data = {}
            for mode in (Mode.WALK, Mode.CYCLE, Mode.CAR):
                routes = await ors.get_routes(o_loc, d_loc, mode)
                modes_data[mode.value] = [
                    {
                        "distance_m": r.distance_m,
                        "duration_s": r.duration_s,
                        "coordinates": simplify_line(r.geometry.coordinates, max_points=300),
                        "waytypes": r.geometry.waytypes,
                    }
                    for r in routes
                ]
                if mode == Mode.WALK and routes:
                    ways = await overpass.get_lighting_ways(routes[0].geometry.coordinates)
                    all_lighting_ways.extend(ways[:30])

            recorded_trips.append(
                {"name": name, "origin": list(orig), "destination": list(dest), "modes": modes_data}
            )

        Path("data/demo/delhi_routes.json").write_text(
            json.dumps({"synthetic": False, "trips": recorded_trips}, indent=2),
            encoding="utf-8",
        )
        Path("data/demo/delhi_lighting.json").write_text(
            json.dumps({"synthetic": False, "ways": all_lighting_ways}, indent=2),
            encoding="utf-8",
        )
        print("Recorded live fixtures to data/demo/delhi_routes.json and delhi_lighting.json")


if __name__ == "__main__":
    asyncio.run(main())
