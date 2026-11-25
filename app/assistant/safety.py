"""Deterministic safety, medical, and out-of-scope detection and static replies."""

import re
from typing import Any

from app.assistant.intents import Intent

_EMERGENCY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcan'?t\s+breathe\b", re.IGNORECASE),
    re.compile(r"\bcannot\s+breathe\b", re.IGNORECASE),
    re.compile(r"\bchest\s+pain\b", re.IGNORECASE),
    re.compile(r"\basthma\s+attack\b", re.IGNORECASE),
    re.compile(r"\bshortness\s+of\s+breath\b", re.IGNORECASE),
    re.compile(r"\bsuffocating\b", re.IGNORECASE),
    re.compile(r"\bchoking\b", re.IGNORECASE),
    re.compile(r"\bmedical\s+emergency\b", re.IGNORECASE),
    re.compile(r"\bblue\s+lips\b", re.IGNORECASE),
)

_MEDICAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\binhaler\b", re.IGNORECASE),
    re.compile(r"\bmedication\b", re.IGNORECASE),
    re.compile(r"\bmedicine\b", re.IGNORECASE),
    re.compile(r"\bprescrib\w*\b", re.IGNORECASE),
    re.compile(r"\bdiagnos\w*\b", re.IGNORECASE),
    re.compile(r"\bnebulizer\b", re.IGNORECASE),
    re.compile(r"\bsteroid\w*\b", re.IGNORECASE),
    re.compile(r"\bshould\s+i\s+take\b", re.IGNORECASE),
    re.compile(r"\btreat\s+my\b", re.IGNORECASE),
    re.compile(r"\bcure\b", re.IGNORECASE),
)

_OUT_OF_SCOPE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(stock\s+market|bitcoin|crypto|forex)\b", re.IGNORECASE),
    re.compile(r"\b(recipe|biryani|pasta|cake)\b", re.IGNORECASE),
    re.compile(r"\b(movie|cricket|football|world\s+cup)\b", re.IGNORECASE),
    re.compile(r"\b(election|politics|president|prime\s+minister)\b", re.IGNORECASE),
    re.compile(r"\b(write\s+code|python\s+script|javascript|homework|essay)\b", re.IGNORECASE),
    re.compile(r"\b(tell\s+me\s+a\s+joke|write\s+a\s+poem)\b", re.IGNORECASE),
)


def detect_safety_intent(message: str) -> Intent | None:
    """Return EMERGENCY, MEDICAL, or OUT_OF_SCOPE if matched, else None."""
    for pat in _EMERGENCY_PATTERNS:
        if pat.search(message):
            return Intent.EMERGENCY
    for pat in _MEDICAL_PATTERNS:
        if pat.search(message):
            return Intent.MEDICAL
    for pat in _OUT_OF_SCOPE_PATTERNS:
        if pat.search(message):
            return Intent.OUT_OF_SCOPE
    return None


def build_static_reply(intent: Intent, country_code: str | None = None) -> dict[str, Any]:
    """Build deterministic static reply (zero Gemini calls) for safety/help intents."""
    if intent == Intent.EMERGENCY:
        num_text = "112" if country_code == "IN" else "your local emergency number (112 in India)"
        return {
            "summary": f"If this is an emergency, call {num_text} now.",
            "recommendation": "Seek immediate medical help and move to cleaner indoor air if able.",
            "reasons": [],
            "caveats": ["BreatheMap is an air-exposure tool, not an emergency service."],
        }

    if intent == Intent.MEDICAL:
        return {
            "summary": "I can't give medical advice; please ask a doctor.",
            "recommendation": (
                "If you'd like, I can check current air quality or suggest ways to lower your "
                "estimated exposure today."
            ),
            "reasons": [],
            "caveats": ["Not medical advice."],
        }

    if intent == Intent.OUT_OF_SCOPE:
        return {
            "summary": (
                "I can only help with air quality, travel exposure comparisons, "
                "outdoor activity timing, indoor air tips, and community pollution reports."
            ),
            "recommendation": "Try asking about the air near you or comparing routes for a trip.",
            "reasons": [],
            "caveats": [],
        }

    # GREETING / help
    return {
        "summary": (
            "Hi! I'm BreatheMap's air-exposure assistant. I can check local air quality, "
            "find cleaner hours, compare travel modes, and share indoor air tips."
        ),
        "recommendation": "Ask me about the air near you or where you're travelling today.",
        "reasons": [],
        "caveats": [],
    }
