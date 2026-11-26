"""Deterministic Quick-answer templates built from structured card data (Section 8.14)."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.assistant.intents import Intent


def _hhmm(val: Any) -> str:
    if isinstance(val, datetime):
        return val.strftime("%H:%M")
    return str(val)[11:16]


def _card_data(cards: list[dict[str, Any]], card_type: str) -> Any:
    for card in cards:
        if card.get("type") == card_type:
            return card.get("data")
    return None


def _short_location(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    raw = str(context.get("location_label") or context.get("label") or "").strip()
    if not raw:
        return ""
    return raw.split(",")[0].strip()[:40]


def _reply_air_now(
    cards: list[dict[str, Any]], caveats: list[str], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    air = _card_data(cards, "air_summary") or {}
    band = air.get("band", "Unavailable")
    idx = air.get("index", "--")
    pm25 = air.get("pm25", "--")
    place = _short_location(context)
    where = f" in {place}" if place else ""
    msg = str((context or {}).get("user_message") or "").lower()
    if "mask" in msg:
        rec = (
            "Consider wearing a well-fitted N95/KN95 mask outdoors and check the cleanest "
            "3-hour window."
            if str(air.get("level", "L1")) >= "L3"
            else "Air is relatively clean right now; a mask is optional unless you are sensitive."
        )
    else:
        rec = "Check the cleanest 3-hour window before planning outdoor time."
    return {
        "summary": f"Current air quality{where} is {band} (index {idx}, PM2.5 {pm25} µg/m³).",
        "recommendation": rec,
        "reasons": [f"Modelled data ({air.get('source', 'Open-Meteo')})."],
        "caveats": caveats,
    }


def _reply_best_time(
    cards: list[dict[str, Any]], caveats: list[str], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    win = _card_data(cards, "time_window") or {}
    clean = win.get("cleanest")
    worst = win.get("worst")
    place = _short_location(context)
    where = f" near {place}" if place else ""
    if clean:
        c_start = _hhmm(clean["start_time"])
        c_end = _hhmm(clean["end_time"])
        summary = (
            f"Cleanest 3-hour window{where} is {c_start}-{c_end} "
            f"(about {clean['avg_pm25']} µg/m³ PM2.5)."
        )
    else:
        summary = f"Cleanest window{where} is shown in the outlook card."
    reasons: list[str] = []
    if worst:
        reasons.append(
            f"Peak smog window: {_hhmm(worst['start_time'])}-{_hhmm(worst['end_time'])} "
            f"({worst['avg_pm25']} µg/m³)."
        )
    return {
        "summary": summary,
        "recommendation": "Plan outdoor errands during the cleanest window.",
        "reasons": reasons,
        "caveats": caveats,
    }


def _reply_activity(
    cards: list[dict[str, Any]], caveats: list[str], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    adv = _card_data(cards, "activity_advice") or {}
    win = _card_data(cards, "time_window") or {}
    clean = win.get("cleanest")
    rec = str(adv.get("advice", "Consider a lighter or shorter session."))
    place = _short_location(context)
    dur = adv.get("duration_min") or (context or {}).get("duration_min")
    act = str(adv.get("activity") or (context or {}).get("activity") or "outdoor activity")
    dur_note = f" for {dur} min" if dur else ""
    where = f" in {place}" if place else ""
    reasons = [str(adv["cautious_note"])] if adv.get("cautious_note") else []
    if clean:
        reasons.append(
            f"Cleanest window: {_hhmm(clean['start_time'])}-{_hhmm(clean['end_time'])} "
            f"({clean['avg_pm25']} µg/m³ PM2.5)."
        )
    return {
        "summary": f"For your {act}{dur_note}{where}: {adv.get('summary', 'Activity guidance')}.",
        "recommendation": rec,
        "reasons": reasons[:4],
        "caveats": [*caveats, "Not medical advice."][:3],
    }


def _reply_route(
    cards: list[dict[str, Any]], caveats: list[str], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    route = _card_data(cards, "route_comparison") or {}
    dest_label = str((route.get("destination") or {}).get("label") or "").split(",")[0].strip()
    options = [o for o in route.get("options", []) if o.get("status") == "available"]
    if not options:
        return {
            "summary": "No routed options were available for this trip.",
            "recommendation": "Try nearby landmarks or check again shortly.",
            "reasons": [],
            "caveats": caveats,
        }
    best = min(options, key=lambda o: o["dose_ug"])
    fastest = min(options, key=lambda o: o["duration_min"])
    est_note = " (estimate)" if best.get("is_estimated") else ""
    to_note = f" to {dest_label}" if dest_label else ""
    summary = (
        f"For your trip{to_note}, lowest estimated exposure is "
        f"{best['mode'].capitalize()}{est_note} "
        f"— about {best['dose_ug']} µg PM2.5 over {best['duration_min']} min. "
        f"Fastest: {fastest['mode'].capitalize()} ({fastest['duration_min']} min)."
    )
    sug = route.get("departure_suggestion")
    rec = (
        f"Leaving at {sug['time'][11:16]} could lower your estimate by about "
        f"{sug['reduction_pct']}%."
        if sug
        else f"Choose {best['mode']} for lower estimated exposure."
    )
    return {
        "summary": summary,
        "recommendation": rec,
        "reasons": [],
        "caveats": caveats,
    }


def _reply_home_tips(
    cards: list[dict[str, Any]], caveats: list[str], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    tips = _card_data(cards, "home_tips") or []
    place = _short_location(context)
    where = f" in {place}" if place else ""
    top = tips[0]["title"] if tips else "Keep windows closed during peak smog"
    return {
        "summary": f"Based on current air{where}, here are {len(tips)} practical indoor air tips.",
        "recommendation": f"Start with: {top}.",
        "reasons": [t["title"] for t in tips[:3]],
        "caveats": caveats,
    }


def _reply_reports(
    cards: list[dict[str, Any]], caveats: list[str], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    reports = _card_data(cards, "reports") or []
    place = _short_location(context)
    where = f" near {place}" if place else " nearby"
    if not reports:
        return {
            "summary": f"No unverified community reports{where} in the last 24 hours.",
            "recommendation": "You can view or submit observations on BreatheWatch.",
            "reasons": [],
            "caveats": caveats,
        }
    return {
        "summary": f"Found {len(reports)} unverified community report(s){where} within 3 km.",
        "recommendation": "Check the reports card for categories and distances.",
        "reasons": [],
        "caveats": ["All community reports are unverified."],
    }


def _reply_report_help(
    _cards: list[dict[str, Any]], _caveats: list[str], _context: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "summary": "You can share local smoke, dust, or burning observations on BreatheWatch.",
        "recommendation": "Open the prefilled BreatheWatch form to review and post publicly.",
        "reasons": ["Posting always requires your confirmation step first."],
        "caveats": [],
    }


def _reply_explain(
    cards: list[dict[str, Any]], _caveats: list[str], _context: dict[str, Any] | None = None
) -> dict[str, Any]:
    gloss = _card_data(cards, "glossary") or {}
    term = str(gloss.get("term", "pm25")).upper()
    definition = str(gloss.get("definition", ""))
    return {
        "summary": f"{term}: {definition}",
        "recommendation": "Ask about current air quality or routes anytime.",
        "reasons": [],
        "caveats": [],
    }


_QUICK_BUILDERS: dict[
    Intent, Callable[[list[dict[str, Any]], list[str], dict[str, Any] | None], dict[str, Any]]
] = {
    Intent.AIR_NOW: _reply_air_now,
    Intent.BEST_TIME: _reply_best_time,
    Intent.ACTIVITY_ADVICE: _reply_activity,
    Intent.ROUTE_COMPARE: _reply_route,
    Intent.HOME_TIPS: _reply_home_tips,
    Intent.REPORTS_NEARBY: _reply_reports,
    Intent.REPORT_HELP: _reply_report_help,
    Intent.EXPLAIN: _reply_explain,
}


def build_quick_reply(
    intent: Intent,
    *,
    cards: list[dict[str, Any]],
    warnings: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic reply for any intent without calling Gemini."""
    caveats = list(warnings[:3]) if warnings else []
    builder = _QUICK_BUILDERS.get(intent)
    if builder is not None:
        return builder(cards, caveats, context)
    return {
        "summary": "Air exposure guidance is ready in the cards below.",
        "recommendation": "Ask a specific question about air, routes, or indoor tips.",
        "reasons": [],
        "caveats": caveats,
    }
