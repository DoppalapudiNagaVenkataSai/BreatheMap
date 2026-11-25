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


def _reply_air_now(cards: list[dict[str, Any]], caveats: list[str]) -> dict[str, Any]:
    air = _card_data(cards, "air_summary") or {}
    band = air.get("band", "Unavailable")
    idx = air.get("index", "--")
    pm25 = air.get("pm25", "--")
    return {
        "summary": f"Current air quality is {band} (index {idx}, PM2.5 {pm25} µg/m³).",
        "recommendation": "Check the cleanest 3-hour window before planning outdoor time.",
        "reasons": [f"Modelled data ({air.get('source', 'Open-Meteo')})."],
        "caveats": caveats,
    }


def _reply_best_time(cards: list[dict[str, Any]], caveats: list[str]) -> dict[str, Any]:
    win = _card_data(cards, "time_window") or {}
    clean = win.get("cleanest")
    worst = win.get("worst")
    if clean:
        c_start = _hhmm(clean["start_time"])
        c_end = _hhmm(clean["end_time"])
        summary = (
            f"Cleanest 3-hour window is {c_start}-{c_end} (about {clean['avg_pm25']} µg/m³ PM2.5)."
        )
    else:
        summary = "Cleanest window is shown in the outlook card."
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


def _reply_activity(cards: list[dict[str, Any]], caveats: list[str]) -> dict[str, Any]:
    adv = _card_data(cards, "activity_advice") or {}
    win = _card_data(cards, "time_window") or {}
    clean = win.get("cleanest")
    rec = str(adv.get("advice", "Consider a lighter or shorter session."))
    reasons = [str(adv["cautious_note"])] if adv.get("cautious_note") else []
    if clean:
        reasons.append(
            f"Cleanest window: {_hhmm(clean['start_time'])}-{_hhmm(clean['end_time'])} "
            f"({clean['avg_pm25']} µg/m³ PM2.5)."
        )
    return {
        "summary": f"{adv.get('summary', 'Activity guidance')}. {rec}",
        "recommendation": rec,
        "reasons": reasons[:4],
        "caveats": [*caveats, "Not medical advice."][:3],
    }


def _reply_route(cards: list[dict[str, Any]], caveats: list[str]) -> dict[str, Any]:
    route = _card_data(cards, "route_comparison") or {}
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
    summary = (
        f"Lowest estimated exposure: {best['mode'].capitalize()}{est_note} - "
        f"about {best['dose_ug']} µg PM2.5 over {best['duration_min']} min. "
        f"Fastest: {fastest['mode'].capitalize()} - {fastest['duration_min']} min."
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


def _reply_home_tips(cards: list[dict[str, Any]], caveats: list[str]) -> dict[str, Any]:
    tips = _card_data(cards, "home_tips") or []
    top = tips[0]["title"] if tips else "Keep windows closed during peak smog"
    return {
        "summary": f"Found {len(tips)} practical indoor air tips for current conditions.",
        "recommendation": f"Start with: {top}.",
        "reasons": [t["title"] for t in tips[:3]],
        "caveats": caveats,
    }


def _reply_reports(cards: list[dict[str, Any]], caveats: list[str]) -> dict[str, Any]:
    reports = _card_data(cards, "reports") or []
    if not reports:
        return {
            "summary": "No unverified community reports nearby in the last 24 hours.",
            "recommendation": "You can view or submit observations on BreatheWatch.",
            "reasons": [],
            "caveats": caveats,
        }
    return {
        "summary": f"Found {len(reports)} unverified community report(s) within 3 km.",
        "recommendation": "Check the reports card for categories and distances.",
        "reasons": [],
        "caveats": ["All community reports are unverified."],
    }


def _reply_report_help(_cards: list[dict[str, Any]], _caveats: list[str]) -> dict[str, Any]:
    return {
        "summary": "You can share local smoke, dust, or burning observations on BreatheWatch.",
        "recommendation": "Open the prefilled BreatheWatch form to review and post publicly.",
        "reasons": ["Posting always requires your confirmation step first."],
        "caveats": [],
    }


def _reply_explain(cards: list[dict[str, Any]], _caveats: list[str]) -> dict[str, Any]:
    gloss = _card_data(cards, "glossary") or {}
    term = str(gloss.get("term", "pm25")).upper()
    definition = str(gloss.get("definition", ""))
    return {
        "summary": f"{term}: {definition}",
        "recommendation": "Ask about current air quality or routes anytime.",
        "reasons": [],
        "caveats": [],
    }


_QUICK_BUILDERS: dict[Intent, Callable[[list[dict[str, Any]], list[str]], dict[str, Any]]] = {
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
) -> dict[str, Any]:
    """Build deterministic reply for any intent without calling Gemini."""
    caveats = list(warnings[:3]) if warnings else []
    builder = _QUICK_BUILDERS.get(intent)
    if builder is not None:
        return builder(cards, caveats)
    return {
        "summary": "Air exposure guidance is ready in the cards below.",
        "recommendation": "Ask a specific question about air, routes, or indoor tips.",
        "reasons": [],
        "caveats": caveats,
    }
