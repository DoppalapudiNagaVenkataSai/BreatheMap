"""Thin deterministic tool adapters for the BreatheMap assistant."""

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.assistant.facts import FactsBundle
from app.domain.advice import advise
from app.domain.home_tips import load_tips, select_tips
from app.domain.models import Activity, LatLon, Level, Mode, Scale, SensitiveGroup, SortOption
from app.services.air_service import AirService
from app.services.report_service import ReportService
from app.services.route_service import RouteService

DATA_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge"


def _hhmm(val: Any) -> str:
    if isinstance(val, datetime):
        return val.strftime("%H:%M")
    return str(val)[11:16]


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, str]:
    path = DATA_KNOWLEDGE_DIR / "glossary.json"
    if not path.exists():
        return {}
    data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return data


async def run_air_tool(
    air_service: AirService,
    *,
    lat: float,
    lon: float,
    scale: Scale,
    is_demo: bool,
    bundle: FactsBundle,
    include_windows: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch air quality and optional cleanest/worst windows, populating facts and cards."""
    air_data = await air_service.get_air(LatLon(lat=lat, lon=lon), scale=scale, is_demo=is_demo)
    prov = air_data.get("provenance", {})
    source_label = str(prov.get("source", "Open-Meteo CAMS"))
    observed_at = str(prov.get("observed_at", ""))
    bundle.warnings.extend(prov.get("warnings", []))

    pm25 = air_data.get("pollutants", {}).get("pm25")
    bundle.add_fact("aqi_index", air_data.get("index"), unit=scale.value, source=source_label)
    bundle.add_fact("aqi_band", air_data.get("band"), source=source_label)
    bundle.add_fact("aqi_level", air_data.get("level"), source=source_label)
    bundle.add_fact("pm25", pm25, unit="µg/m³", source=source_label)
    bundle.add_fact("observed_at", observed_at, source=source_label)

    cards: list[dict[str, Any]] = [
        {
            "type": "air_summary",
            "data": {
                "index": air_data.get("index"),
                "scale": scale.value,
                "band": air_data.get("band"),
                "level": air_data.get("level"),
                "pm25": pm25,
                "dominant_pollutant": air_data.get("dominant_pollutant"),
                "observed_at": observed_at,
                "source": source_label,
                "is_demo": is_demo,
            },
        }
    ]

    if include_windows:
        windows = air_data.get("windows", {})
        cleanest = windows.get("cleanest")
        worst = windows.get("worst")
        if cleanest:
            bundle.add_fact(
                "cleanest_window",
                f"{_hhmm(cleanest['start_time'])}-{_hhmm(cleanest['end_time'])}",
                source=source_label,
            )
            bundle.add_fact(
                "cleanest_window_pm25",
                cleanest["avg_pm25"],
                unit="µg/m³",
                source=source_label,
            )
        if worst:
            bundle.add_fact(
                "worst_window",
                f"{_hhmm(worst['start_time'])}-{_hhmm(worst['end_time'])}",
                source=source_label,
            )
            bundle.add_fact(
                "worst_window_pm25",
                worst["avg_pm25"],
                unit="µg/m³",
                source=source_label,
            )
        cards.append({"type": "time_window", "data": windows})

    return air_data, cards


async def run_activity_tool(
    air_service: AirService,
    *,
    lat: float,
    lon: float,
    scale: Scale,
    activity_str: str,
    duration_min: int,
    sensitive: list[SensitiveGroup],
    is_demo: bool,
    bundle: FactsBundle,
) -> list[dict[str, Any]]:
    """Run air lookup and deterministic activity advice rules."""
    air_data, cards = await run_air_tool(
        air_service,
        lat=lat,
        lon=lon,
        scale=scale,
        is_demo=is_demo,
        bundle=bundle,
        include_windows=True,
    )
    level_str = str(air_data.get("level", "L3"))
    level = Level(level_str)
    try:
        activity = Activity(activity_str)
    except ValueError:
        activity = Activity.WALK

    advice_res = advise(level=level, activity=activity, sensitive_groups=sensitive or None)
    bundle.add_fact("activity", activity.value, source="rule")
    bundle.add_fact("duration_min", duration_min, unit="min", source="user")
    bundle.add_fact("effective_level", advice_res.level.value, source="rule")
    bundle.add_fact("activity_advice", advice_res.advice, source="rule")
    if advice_res.cautious_note:
        bundle.add_fact("cautious_note", advice_res.cautious_note, source="rule")

    cards.append(
        {
            "type": "activity_advice",
            "data": {
                "activity": activity.value,
                "duration_min": duration_min,
                "level": advice_res.level.value,
                "summary": advice_res.summary,
                "advice": advice_res.advice,
                "cautious_note": advice_res.cautious_note,
                "not_medical_advice": True,
            },
        }
    )
    return cards


async def run_route_tool(
    route_service: RouteService,
    *,
    origin_lat: float,
    origin_lon: float,
    destination: LatLon | None,
    destination_text: str | None,
    departure_time: datetime | None,
    modes: list[Mode] | None,
    sensitive: list[SensitiveGroup],
    scale: Scale,
    is_demo: bool,
    bundle: FactsBundle,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compare routes deterministically and populate route facts and cards."""
    result = await route_service.compare(
        origin_coord=LatLon(lat=origin_lat, lon=origin_lon),
        dest_coord=destination,
        dest_text=destination_text,
        departure_time=departure_time,
        modes=modes,
        sort_by=SortOption.LEAST_POLLUTION,
        is_demo=is_demo,
    )
    prov = result.get("provenance", {})
    source_label = str(prov.get("source", "Open-Meteo + ORS/OSRM"))
    bundle.warnings.extend(prov.get("warnings", []))

    bundle.add_fact("origin", result["origin"]["label"], source=source_label)
    bundle.add_fact("destination", result["destination"]["label"], source=source_label)
    bundle.add_fact("departure_time", result["departure_time"][11:16], source=source_label)

    for opt in result.get("options", []):
        if opt.get("status") != "available":
            continue
        is_est = bool(opt.get("is_estimated", False))
        mode_name = str(opt["mode"])
        bundle.add_fact(
            f"{mode_name}_dose_ug",
            opt["dose_ug"],
            unit="µg PM2.5",
            source=source_label,
            is_estimated=is_est,
        )
        bundle.add_fact(
            f"{mode_name}_duration_min",
            opt["duration_min"],
            unit="min",
            source=source_label,
            is_estimated=is_est,
        )

    dep_sug = result.get("departure_suggestion")
    if dep_sug:
        bundle.add_fact("suggested_departure", dep_sug["time"][11:16], source=source_label)
        bundle.add_fact(
            "suggested_reduction_pct", dep_sug["reduction_pct"], unit="%", source=source_label
        )

    reports = result.get("reports_along_route", [])
    bundle.user_reports = reports
    bundle.add_fact("reports_along_route_count", len(reports), source="community")

    cards: list[dict[str, Any]] = [
        {"type": "route_comparison", "data": result},
    ]
    if reports:
        cards.append({"type": "reports", "data": reports})
    return result, cards


async def run_home_tips_tool(
    air_service: AirService,
    *,
    lat: float,
    lon: float,
    scale: Scale,
    is_demo: bool,
    bundle: FactsBundle,
) -> list[dict[str, Any]]:
    """Fetch current air level and select indoor home exposure tips."""
    air_data, cards = await run_air_tool(
        air_service,
        lat=lat,
        lon=lon,
        scale=scale,
        is_demo=is_demo,
        bundle=bundle,
        include_windows=True,
    )
    level = Level(str(air_data.get("level", "L3")))
    all_tips = load_tips(DATA_KNOWLEDGE_DIR / "home_tips.json")
    selected = select_tips(all_tips, level=level, limit=5)

    for tip in selected:
        bundle.add_fact(f"tip_{tip.id}", tip.title, source="knowledge")

    cards.append(
        {
            "type": "home_tips",
            "data": [tip.model_dump() for tip in selected],
        }
    )
    return cards


async def run_reports_tool(
    report_service: ReportService,
    *,
    lat: float,
    lon: float,
    is_demo: bool,
    bundle: FactsBundle,
) -> list[dict[str, Any]]:
    """Fetch nearby community reports and populate facts/cards."""
    reports, warnings = await report_service.list_nearby(
        lat=lat, lon=lon, radius_km=3.0, hours=24, is_demo=is_demo
    )
    bundle.warnings.extend(warnings)
    bundle.user_reports = reports
    bundle.add_fact("nearby_reports_count", len(reports), source="community")
    return [{"type": "reports", "data": reports}]


def run_explain_tool(topic: str | None, bundle: FactsBundle) -> list[dict[str, Any]]:
    """Look up glossary definition for a pollutant or exposure term."""
    glossary = _load_glossary()
    key = topic if topic and topic in glossary else "pm25"
    definition = glossary.get(key, "Fine particulate matter (PM2.5).")
    bundle.add_fact(f"glossary_{key}", definition, source="glossary")
    return [
        {
            "type": "glossary",
            "data": {"term": key, "definition": definition},
        }
    ]


def get_utc_now() -> datetime:
    """Return current UTC datetime (extracted for clean testability)."""
    return datetime.now(UTC)
