"""BreatheRoute service orchestrating routing, exposure, lighting, and ranking."""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.constants import (
    F_MODE_CAR,
    F_MODE_CYCLE,
    F_MODE_WALK,
    LIGHTING_CACHE_TTL,
    MAX_ROUTE_DISTANCE_KM,
    MIN_ROUTE_DISTANCE_M,
    ROUTE_CACHE_TTL,
    V_MODE_CAR,
    V_MODE_CYCLE,
    V_MODE_WALK,
)
from app.core.cache import get_or_set, make_cache_key
from app.core.errors import ProviderUnavailableError, StorageUnavailableError, ValidationAppError
from app.domain.exposure import (
    AirPoint,
    Segment,
    concentration_at_point,
    estimate_dose,
    segment_route,
)
from app.domain.geo import (
    geohash_encode,
    geohash_neighbors,
    haversine_m,
    line_midpoint,
    point_to_segment_distance_m,
    simplify_line,
)
from app.domain.lighting import summarize_lighting
from app.domain.models import LatLon, Mode, ModeResult, RouteGeometry, SortOption
from app.domain.modes import emissions_kg, estimate_auto, estimate_bus, estimate_metro
from app.domain.ranking import rank_modes
from app.domain.timeutils import is_night
from app.domain.windows import optimize_departure
from app.providers.base import (
    AirProvider,
    GeocodeProvider,
    LightingProvider,
    RawRoute,
    RoutingProvider,
    WeatherProvider,
)
from app.providers.photon import CompositeGeocodeProvider
from app.services.report_service import _format_public_report, _parse_dt, load_demo_reports
from app.storage.base import CacheStore, ReportStore

MODE_PROFILES: dict[Mode, tuple[float, float]] = {
    Mode.WALK: (V_MODE_WALK, F_MODE_WALK),
    Mode.CYCLE: (V_MODE_CYCLE, F_MODE_CYCLE),
    Mode.CAR: (V_MODE_CAR, F_MODE_CAR),
}


def _parse_air_point(coord: tuple[float, float], air_raw: dict[str, Any]) -> AirPoint:
    hourly = air_raw.get("hourly", {})
    time_strs = hourly.get("time", [])
    times = [datetime.fromisoformat(t).replace(tzinfo=UTC) for t in time_strs]
    values = hourly.get("pm2_5", [])
    return AirPoint(coord=coord, times=times, values=values)


def _check_night_trip(
    departure: datetime, duration_min: float, weather_raw: dict[str, Any]
) -> bool:
    daily = weather_raw.get("daily", {})
    sunrises = daily.get("sunrise", [])
    sunsets = daily.get("sunset", [])
    if not sunrises or not sunsets:
        return False
    sr = datetime.fromisoformat(sunrises[0]).replace(tzinfo=UTC)
    ss = datetime.fromisoformat(sunsets[0]).replace(tzinfo=UTC)
    end_dt = departure + timedelta(minutes=duration_min)
    return is_night(departure, end_dt, sr, ss)


_COORD_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$")


def _parse_lat_lon_text(text: str) -> LatLon | None:
    """Parse 'lat, lon' coordinate strings directly if within valid bounds."""
    match = _COORD_RE.match(text)
    if not match:
        return None
    lat = float(match.group(1))
    lon = float(match.group(2))
    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
        return LatLon(lat=lat, lon=lon)
    return None


class RouteService:
    """Orchestrates multi-mode exposure comparison and route optimization."""

    def __init__(
        self,
        air_provider: AirProvider,
        weather_provider: WeatherProvider,
        geo_provider: GeocodeProvider,
        primary_router: RoutingProvider,
        fallback_router: RoutingProvider | None = None,
        lighting_provider: LightingProvider | None = None,
        cache_store: CacheStore | None = None,
        report_store: ReportStore | None = None,
    ) -> None:
        self.air_provider = air_provider
        self.weather_provider = weather_provider
        self.geo_provider = geo_provider
        self.primary_router = primary_router
        self.fallback_router = fallback_router
        self.lighting_provider = lighting_provider
        self.cache_store = cache_store
        self.report_store = report_store

    async def _resolve_point(
        self,
        coord: LatLon | None,
        text: str | None,
        label_name: str,
        bias: LatLon | None = None,
    ) -> tuple[LatLon, str]:
        if coord is not None:
            return coord, f"{coord.lat:.4f}, {coord.lon:.4f}"
        if text:
            parsed_coord = _parse_lat_lon_text(text)
            if parsed_coord is not None:
                return parsed_coord, f"{parsed_coord.lat:.4f}, {parsed_coord.lon:.4f}"
            if bias is not None and isinstance(self.geo_provider, CompositeGeocodeProvider):
                results = await self.geo_provider.search(text, lat=bias.lat, lon=bias.lon)
            else:
                results = await self.geo_provider.search(text)
            if not results:
                raise ValidationAppError(
                    f"No places found for '{text}'. Try a nearby landmark or area name."
                )
            first = results[0]
            return LatLon(lat=float(first["lat"]), lon=float(first["lon"])), str(
                first.get("label", text)
            )
        raise ValidationAppError(f"Missing {label_name} coordinates or text.")

    def _validate_departure(
        self, departure_time: datetime | None, now: datetime
    ) -> tuple[datetime, list[str]]:
        warnings: list[str] = []
        if departure_time is None:
            return now, warnings
        dep = (
            departure_time.astimezone(UTC)
            if departure_time.tzinfo
            else departure_time.replace(tzinfo=UTC)
        )
        if dep < now - timedelta(minutes=10):
            warnings.append("Departure time was in the past; using now.")
            return now, warnings
        if dep > now + timedelta(hours=48):
            raise ValidationAppError(
                "Forecasts reach 48 hours ahead; please choose an earlier time."
            )
        return dep, warnings

    async def _fetch_mode_routes(
        self, origin: LatLon, destination: LatLon, mode: Mode
    ) -> tuple[list[RawRoute], list[str]]:
        cache_key = make_cache_key(
            "route",
            {
                "o": [round(origin.lat, 4), round(origin.lon, 4)],
                "d": [round(destination.lat, 4), round(destination.lon, 4)],
                "m": mode.value,
            },
        )
        warnings: list[str] = []

        async def _load() -> dict[str, Any]:
            used_fallback = False
            try:
                routes = await self.primary_router.get_routes(origin, destination, mode)
            except ProviderUnavailableError:
                if self.fallback_router is None:
                    return {"routes": [], "fallback": False, "failed": True}
                try:
                    routes = await self.fallback_router.get_routes(origin, destination, mode)
                    used_fallback = True
                except ProviderUnavailableError:
                    return {"routes": [], "fallback": True, "failed": True}

            serialized = [
                {
                    "distance_m": r.distance_m,
                    "duration_s": r.duration_s,
                    "coordinates": r.geometry.coordinates,
                    "waytypes": r.geometry.waytypes,
                }
                for r in routes
            ]
            return {"routes": serialized, "fallback": used_fallback, "failed": False}

        data = await get_or_set(self.cache_store, cache_key, ROUTE_CACHE_TTL, _load)
        if data.get("fallback") and not data.get("failed"):
            warnings.append(
                "Primary routing unavailable; using fallback routing without road-type factors."
            )
        routes = [
            RawRoute(
                distance_m=float(item["distance_m"]),
                duration_s=float(item["duration_s"]),
                geometry=RouteGeometry(
                    coordinates=[(float(p[0]), float(p[1])) for p in item["coordinates"]],
                    waytypes=item.get("waytypes"),
                ),
            )
            for item in data.get("routes", [])
        ]
        return routes, warnings

    async def _fetch_air_points(
        self, origin: LatLon, mid: LatLon, destination: LatLon
    ) -> tuple[list[AirPoint], dict[str, Any]]:
        pts = [origin, mid, destination]
        unique_keys: dict[tuple[float, float], LatLon] = {}
        for p in pts:
            rounded = (round(p.lat, 2), round(p.lon, 2))
            if rounded not in unique_keys:
                unique_keys[rounded] = p

        air_tasks = [self.air_provider.get_air(p) for p in unique_keys.values()]
        weather_task = self.weather_provider.get_weather(origin)
        results = await asyncio.gather(*air_tasks, weather_task)

        air_raws = results[:-1]
        weather_raw: dict[str, Any] = results[-1]
        air_points = [
            _parse_air_point((loc.lat, loc.lon), raw)
            for loc, raw in zip(unique_keys.values(), air_raws, strict=False)
        ]
        return air_points, weather_raw

    async def _get_lighting_summary(
        self, segments: list[Segment], coords: list[tuple[float, float]]
    ) -> tuple[Any, list[str]]:
        if not self.lighting_provider or len(coords) < 2:
            return None, []
        cache_key = make_cache_key(
            "lighting",
            {"pts": [(round(c[0], 4), round(c[1], 4)) for c in simplify_line(coords, 30)]},
        )
        try:
            data = await get_or_set(
                self.cache_store,
                cache_key,
                LIGHTING_CACHE_TTL,
                lambda: self._fetch_ways(coords),
            )
            ways = data.get("ways", [])
            return summarize_lighting(segments, ways), []
        except ProviderUnavailableError:
            return summarize_lighting(segments, []), [
                "Street-lighting lookup timed out; lighting marked unknown."
            ]

    async def _fetch_ways(self, coords: list[tuple[float, float]]) -> dict[str, Any]:
        if not self.lighting_provider:
            return {"ways": []}
        ways = await self.lighting_provider.get_lighting_ways(coords)
        return {"ways": ways}

    async def _load_route_report_candidates(
        self,
        coords: list[tuple[float, float]],
        is_demo: bool,
        ref_now: datetime,
        warnings: list[str] | None,
    ) -> list[dict[str, Any]]:
        if is_demo:
            return load_demo_reports(now=ref_now)
        if not self.report_store:
            return []
        mid = line_midpoint(coords)
        gh = geohash_encode(mid[0], mid[1], precision=5)
        buckets = [gh, *geohash_neighbors(gh)]
        try:
            return await self.report_store.list_nearby(buckets, max_results=50)
        except StorageUnavailableError:
            if warnings is not None:
                warnings.append("Community reports along route are temporarily unavailable.")
            return []

    async def _find_reports_along_route(
        self,
        coords: list[tuple[float, float]],
        is_demo: bool = False,
        now: datetime | None = None,
        warnings: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not coords:
            return []
        ref_now = now or datetime.now(UTC)
        candidates = await self._load_route_report_candidates(coords, is_demo, ref_now, warnings)
        matched: list[dict[str, Any]] = []
        for rep in candidates:
            if rep.get("status") != "published":
                continue
            expires_at = _parse_dt(rep.get("expires_at"))
            if expires_at is not None and expires_at <= ref_now:
                continue
            rlat, rlon = rep.get("lat"), rep.get("lon")
            if rlat is None or rlon is None:
                continue
            for i in range(len(coords) - 1):
                d = point_to_segment_distance_m(
                    float(rlat),
                    float(rlon),
                    coords[i][0],
                    coords[i][1],
                    coords[i + 1][0],
                    coords[i + 1][1],
                )
                if d <= 200.0:
                    matched.append(_format_public_report(rep))
                    break
        return matched

    async def _score_routed_modes(
        self,
        route_results_map: dict[Mode, tuple[list[RawRoute], list[str]]],
        selected_modes: list[Mode],
        air_points: list[AirPoint],
        dep_time: datetime,
        is_night_trip: bool,
        global_warnings: list[str],
    ) -> tuple[list[ModeResult], ModeResult | None, dict[Mode, tuple[list[Segment], float, float]]]:
        options: list[ModeResult] = []
        car_best: ModeResult | None = None
        routed_best_segs: dict[Mode, tuple[list[Segment], float, float]] = {}

        for m in (Mode.WALK, Mode.CYCLE, Mode.CAR):
            if m not in route_results_map:
                continue
            raw_list, m_warnings = route_results_map[m]
            global_warnings.extend(m_warnings)
            if not raw_list:
                if m in selected_modes:
                    options.append(self._unavailable_mode(m, "Route unavailable for this mode."))
                continue

            best_mr, best_segs = self._pick_best_alternative(m, raw_list, air_points, dep_time)
            if is_night_trip and m in (Mode.WALK, Mode.CYCLE):
                coords = best_mr.geometry.coordinates if best_mr.geometry else []
                lighting, l_warn = await self._get_lighting_summary(best_segs, coords)
                best_mr.lighting = lighting
                global_warnings.extend(l_warn)

            if m == Mode.CAR:
                car_best = best_mr
            if m in selected_modes:
                options.append(best_mr)
                v_m, f_m = MODE_PROFILES[m]
                routed_best_segs[m] = (best_segs, v_m, f_m)

        return options, car_best, routed_best_segs

    def _pick_best_alternative(
        self,
        mode: Mode,
        raw_list: list[RawRoute],
        air_points: list[AirPoint],
        dep_time: datetime,
    ) -> tuple[ModeResult, list[Segment]]:
        v_m, f_m = MODE_PROFILES[mode]
        scored: list[tuple[ModeResult, list[Segment]]] = []
        for raw in raw_list:
            segs = segment_route(raw.geometry.coordinates, raw.duration_s, raw.geometry.waytypes)
            dose, avg_c = estimate_dose(segs, v_m, f_m, air_points, dep_time)
            dist_km = round(raw.distance_m / 1000.0, 2)
            dur_min = round(raw.duration_s / 60.0, 1)
            simp_coords = simplify_line(raw.geometry.coordinates, max_points=300)
            mr = ModeResult(
                mode=mode,
                is_estimated=False,
                duration_min=dur_min,
                distance_km=dist_km,
                dose_ug=dose,
                avg_pm25=avg_c,
                emissions_kg_co2e=emissions_kg(mode, dist_km),
                geometry=RouteGeometry(coordinates=simp_coords, waytypes=None),
            )
            scored.append((mr, segs))
        scored.sort(key=lambda pair: pair[0].dose_ug)
        return scored[0]

    @staticmethod
    def _unavailable_mode(mode: Mode, warning: str) -> ModeResult:
        return ModeResult(
            mode=mode,
            is_estimated=mode in (Mode.AUTO, Mode.BUS, Mode.METRO),
            duration_min=0.0,
            distance_km=0.0,
            dose_ug=0.0,
            avg_pm25=0.0,
            status="unavailable",
            warnings=[warning],
        )

    def _append_derived_modes(
        self,
        options: list[ModeResult],
        selected_modes: list[Mode],
        car_best: ModeResult | None,
        origin: LatLon,
        dest: LatLon,
        air_points: list[AirPoint],
        dep_time: datetime,
    ) -> None:
        mid_lat = (origin.lat + dest.lat) / 2.0
        mid_lon = (origin.lon + dest.lon) / 2.0
        avg_amb = concentration_at_point((mid_lat, mid_lon), air_points, dep_time)

        if Mode.AUTO in selected_modes:
            options.append(
                estimate_auto(car_best)
                if car_best
                else self._unavailable_mode(Mode.AUTO, "Route unavailable.")
            )
        if Mode.BUS in selected_modes:
            options.append(
                estimate_bus(car_best, avg_amb)
                if car_best
                else self._unavailable_mode(Mode.BUS, "Route unavailable.")
            )
        if Mode.METRO in selected_modes:
            options.append(
                estimate_metro((origin.lat, origin.lon), (dest.lat, dest.lon), air_points, dep_time)
            )

    @staticmethod
    def _optimize_best_departure(
        available_ranked: list[ModeResult],
        routed_best_segs: dict[Mode, tuple[list[Segment], float, float]],
        air_points: list[AirPoint],
        dep_time: datetime,
        ref_now: datetime,
        flexibility_minutes: int,
    ) -> dict[str, Any] | None:
        if flexibility_minutes <= 0 or not available_ranked:
            return None
        target_opt = available_ranked[0]
        if target_opt.mode not in routed_best_segs:
            return None
        segs, v_m, f_m = routed_best_segs[target_opt.mode]

        def _eval_at(t: datetime) -> float:
            if t < ref_now or t > ref_now + timedelta(hours=48):
                return float("inf")
            d_val, _ = estimate_dose(segs, v_m, f_m, air_points, t)
            return d_val

        opt_res = optimize_departure(_eval_at, dep_time, flexibility_minutes)
        if not opt_res:
            return None
        return {
            "time": opt_res[0].isoformat(),
            "estimated_dose_ug": opt_res[1],
            "reduction_pct": opt_res[2],
        }

    async def compare(
        self,
        origin_coord: LatLon | None = None,
        origin_text: str | None = None,
        dest_coord: LatLon | None = None,
        dest_text: str | None = None,
        departure_time: datetime | None = None,
        flexibility_minutes: int = 120,
        modes: list[Mode] | None = None,
        sort_by: SortOption = SortOption.LEAST_POLLUTION,
        prefer_lit: bool = False,
        is_demo: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Compare modes and routes by estimated PM2.5 inhaled."""
        ref_now = now or datetime.now(tz=UTC)
        origin, orig_label = await self._resolve_point(origin_coord, origin_text, "origin")
        dest, dest_label = await self._resolve_point(
            dest_coord, dest_text, "destination", bias=origin
        )

        straight_m = haversine_m(origin.lat, origin.lon, dest.lat, dest.lon)
        if straight_m < MIN_ROUTE_DISTANCE_M:
            raise ValidationAppError("You're already there.")
        if straight_m > MAX_ROUTE_DISTANCE_KM * 1000.0:
            raise ValidationAppError(
                f"BreatheRoute compares local trips up to {int(MAX_ROUTE_DISTANCE_KM)} km."
            )

        dep_time, global_warnings = self._validate_departure(departure_time, ref_now)
        selected_modes = modes or list(Mode)
        mid_pt = LatLon(lat=(origin.lat + dest.lat) / 2.0, lon=(origin.lon + dest.lon) / 2.0)

        need_car = any(m in selected_modes for m in (Mode.CAR, Mode.AUTO, Mode.BUS))
        routed_to_fetch: list[Mode] = [m for m in (Mode.WALK, Mode.CYCLE) if m in selected_modes]
        if need_car:
            routed_to_fetch.append(Mode.CAR)

        gathered = await asyncio.gather(
            self._fetch_air_points(origin, mid_pt, dest),
            *[self._fetch_mode_routes(origin, dest, m) for m in routed_to_fetch],
        )
        air_points, weather_raw = gathered[0]
        route_results_map: dict[Mode, tuple[list[RawRoute], list[str]]] = dict(
            zip(routed_to_fetch, gathered[1:], strict=False)
        )

        is_night_trip = _check_night_trip(dep_time, 30.0, weather_raw)
        options, car_best, routed_best_segs = await self._score_routed_modes(
            route_results_map, selected_modes, air_points, dep_time, is_night_trip, global_warnings
        )
        self._append_derived_modes(
            options, selected_modes, car_best, origin, dest, air_points, dep_time
        )

        ranked = rank_modes(options, sort_by=sort_by, prefer_lit=prefer_lit)
        available_ranked = [o for o in ranked if o.status == "available"]
        dep_suggestion = self._optimize_best_departure(
            available_ranked, routed_best_segs, air_points, dep_time, ref_now, flexibility_minutes
        )

        first_coords = next(
            (
                o.geometry.coordinates
                for o in available_ranked
                if o.geometry and o.geometry.coordinates
            ),
            [],
        )
        reports = await self._find_reports_along_route(
            first_coords, is_demo=is_demo, now=ref_now, warnings=global_warnings
        )
        best_opt = min(available_ranked, key=lambda o: o.dose_ug) if available_ranked else None
        fastest_opt = (
            min(available_ranked, key=lambda o: o.duration_min) if available_ranked else None
        )

        return {
            "origin": {"lat": origin.lat, "lon": origin.lon, "label": orig_label},
            "destination": {"lat": dest.lat, "lon": dest.lon, "label": dest_label},
            "departure_time": dep_time.isoformat(),
            "is_night": is_night_trip,
            "options": [self._serialize_option(o) for o in ranked],
            "best_option": best_opt.mode.value if best_opt else None,
            "fastest_option": fastest_opt.mode.value if fastest_opt else None,
            "departure_suggestion": dep_suggestion,
            "reports_along_route": reports,
            "explanation_facts": {
                "origin": orig_label,
                "destination": dest_label,
                "best_mode": best_opt.mode.value if best_opt else None,
                "best_dose_ug": best_opt.dose_ug if best_opt else None,
                "fastest_mode": fastest_opt.mode.value if fastest_opt else None,
                "is_night": is_night_trip,
                "departure_suggestion": dep_suggestion,
            },
            "provenance": {
                "source": "Delhi sample data" if is_demo else "Open-Meteo + ORS/OSRM",
                "observed_at": ref_now.isoformat(),
                "is_demo": is_demo,
                "warnings": list(dict.fromkeys(global_warnings)),
            },
        }

    @staticmethod
    def _serialize_option(o: ModeResult) -> dict[str, Any]:
        return {
            "mode": o.mode.value,
            "is_estimated": o.is_estimated,
            "duration_min": o.duration_min,
            "distance_km": o.distance_km,
            "dose_ug": o.dose_ug,
            "avg_pm25": o.avg_pm25,
            "vs_best_pct": o.pct_vs_best,
            "is_best": o.is_best,
            "about_same": o.is_about_same,
            "flags": o.flags,
            "lighting": o.lighting.model_dump() if o.lighting else None,
            "emissions_kg": o.emissions_kg_co2e,
            "geometry": (
                {
                    "type": "LineString",
                    "coordinates": [[c[1], c[0]] for c in o.geometry.coordinates],
                }
                if o.geometry
                else None
            ),
            "status": o.status,
            "warnings": o.warnings,
        }
