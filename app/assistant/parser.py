"""Rule-based natural language parser for BreatheMap assistant (Section 8.14)."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.assistant.intents import Intent
from app.assistant.safety import detect_safety_intent
from app.domain.models import Mode, SensitiveGroup

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|good\s+(morning|afternoon|evening)|help|what\s+can\s+you\s+do)"
    r"[\s!?.]*$",
    re.IGNORECASE,
)

_REPORT_HELP_RE = re.compile(
    r"\b(how\s+(do\s+i|to|can\s+i)\s+report|where\s+to\s+report|submit\s+a?\s*report)\b",
    re.IGNORECASE,
)

_REPORTS_NEARBY_RE = re.compile(
    r"\b(any\s+\w*\s*reported|reports?\s+near|reported\s+near|smoke\s+reported|"
    r"burning\s+reported|community\s+reports?)\b",
    re.IGNORECASE,
)

_EXPLAIN_RE = re.compile(
    r"\b(what\s+is|what\s+does|what\s+are|meaning\s+of|explain|define)\b",
    re.IGNORECASE,
)

_HOME_RE = re.compile(
    r"\b(home|indoor|indoors|inside|room|window|windows|purifier|kitchen|incense|mop)\b",
    re.IGNORECASE,
)

_BEST_TIME_RE = re.compile(
    r"\b(cleanest\s+time|best\s+time|worst\s+time|when\s+should\s+i\s+go\s+out|"
    r"when\s+is\s+(?:the\s+)?air\s+cleanest|what\s+time\s+is\s+best)\b",
    re.IGNORECASE,
)

_ROUTE_HINT_RE = re.compile(
    r"\b(best\s+way|compare\s+routes?|commute|going\s+to|go\s+to|travel\s+to|"
    r"get\s+to|reach|from\s+.+\s+to)\b",
    re.IGNORECASE,
)

_MODE_PATTERNS: tuple[tuple[re.Pattern[str], Mode], ...] = (
    (re.compile(r"\b(walk|walking|on\s+foot)\b", re.IGNORECASE), Mode.WALK),
    (re.compile(r"\b(cycle|cycling|bike|biking|bicycle)\b", re.IGNORECASE), Mode.CYCLE),
    (re.compile(r"\b(car|drive|driving|cab|taxi)\b", re.IGNORECASE), Mode.CAR),
    (re.compile(r"\b(auto|auto-rickshaw|rickshaw|tuk-tuk)\b", re.IGNORECASE), Mode.AUTO),
    (re.compile(r"\bbus\b", re.IGNORECASE), Mode.BUS),
    (re.compile(r"\b(metro|subway|city\s+train|train)\b", re.IGNORECASE), Mode.METRO),
)

_ACTIVITY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(jog|jogging|run|running)\b", re.IGNORECASE), "jog"),
    (re.compile(r"\b(walk|walking|stroll|strolling)\b", re.IGNORECASE), "walk"),
    (re.compile(r"\b(cycle|cycling|ride|riding)\b", re.IGNORECASE), "cycle"),
    (re.compile(r"\b(play|playing|playground)\b", re.IGNORECASE), "play"),
    (re.compile(r"\byoga\b", re.IGNORECASE), "yoga"),
    (re.compile(r"\b(workout|exercise|exercising)\b", re.IGNORECASE), "jog"),
)

_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], SensitiveGroup], ...] = (
    (
        re.compile(r"\b(my\s+)?(child|kid|kids|children|baby|toddler|son|daughter)\b", re.I),
        SensitiveGroup.CHILD,
    ),
    (
        re.compile(r"\b(elderly|grandparent|grandmother|grandfather|aged\s+parent)\b", re.I),
        SensitiveGroup.ELDERLY,
    ),
    (
        re.compile(r"\b(asthma|copd|respiratory|lung\s+condition)\b", re.I),
        SensitiveGroup.ASTHMA,
    ),
    (re.compile(r"\bpregnant\b", re.I), SensitiveGroup.PREGNANCY),
)

_GLOSSARY_KEYWORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpm\s*2\.?5\b", re.I), "pm25"),
    (re.compile(r"\bpm\s*10\b", re.I), "pm10"),
    (re.compile(r"\bno2\b", re.I), "no2"),
    (re.compile(r"\bo3|ozone\b", re.I), "o3"),
    (re.compile(r"\bco\b", re.I), "co"),
    (re.compile(r"\bso2\b", re.I), "so2"),
    (re.compile(r"\bnaqi\b", re.I), "naqi"),
    (re.compile(r"\bus\s*aqi\b", re.I), "us_aqi"),
    (re.compile(r"\bexposure|dose\b", re.I), "exposure"),
    (re.compile(r"\binhalation\b", re.I), "inhalation_rate"),
    (re.compile(r"\bmodelled\b", re.I), "modelled_data"),
    (re.compile(r"\binversion\b", re.I), "winter_inversion"),
)

_TIME_IN_RE = re.compile(r"\bin\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b", re.I)
_TIME_AT_RE = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_TIME_24H_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")

_DURATION_RE = re.compile(
    r"\b(?:for\s+)?(\d+(?:\.\d+)?)\s*(minutes?|mins?|min|hours?|hrs?|hr|h)\b",
    re.I,
)

_FROM_TO_RE = re.compile(
    r"\bfrom\s+([A-Za-z0-9\s,.'-]{2,60}?)\s+to\s+([A-Za-z0-9\s,.'-]{2,60}?)"
    r"(?=\s+(?:at|in|on|by|for|this|tomorrow|tonight|now|best|via)\b|[?.!]|$)",
    re.I,
)
_TO_PLACE_RE = re.compile(
    r"\b(?:going\s+to|go\s+to|travel\s+to|get\s+to|reach|head\s+to|commute\s+to|routes?\s+to)\s+"
    r"([A-Za-z0-9\s,.'-]{2,60}?)"
    r"(?=\s+(?:at|in|on|by|for|this|tomorrow|tonight|now|best|via)\b|[?.!]|$)",
    re.I,
)


@dataclass
class ParsedMessage:
    """Structured result of rule-based message and context parsing."""

    intent: Intent
    departure_time: datetime | None = None
    duration_min: int | None = None
    mode: Mode | None = None
    activity: str | None = None
    origin_text: str | None = None
    destination_text: str | None = None
    topic: str | None = None
    sensitive_hints: list[SensitiveGroup] = field(default_factory=list)
    is_time_budget: bool = False


def _resolve_clock_candidate(
    local_now: datetime,
    tz: ZoneInfo,
    hour: int,
    minute: int,
    is_tomorrow: bool,
) -> datetime:
    base_date = local_now.date() + (timedelta(days=1) if is_tomorrow else timedelta(days=0))
    candidate = datetime(base_date.year, base_date.month, base_date.day, hour, minute, tzinfo=tz)
    if not is_tomorrow and candidate < local_now - timedelta(minutes=5):
        candidate += timedelta(days=1)
    return candidate


def parse_time_expression(
    message: str, now: datetime, tz_name: str = "Asia/Kolkata"
) -> datetime | None:
    """Parse relative or clock time expressions in the location's timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    local_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=UTC).astimezone(tz)
    lowered = message.lower()

    if re.search(r"\bnow\b|\bright\s+now\b", lowered):
        return local_now

    in_match = _TIME_IN_RE.search(message)
    if in_match:
        val = float(in_match.group(1))
        unit = in_match.group(2).lower()
        delta = timedelta(hours=val) if unit.startswith("h") else timedelta(minutes=val)
        return local_now + delta

    is_tomorrow = "tomorrow" in lowered
    ampm_match = _TIME_AT_RE.search(message)
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2) or 0)
        ampm = ampm_match.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return _resolve_clock_candidate(local_now, tz, hour, minute, is_tomorrow)

    h24_match = _TIME_24H_RE.search(message)
    if h24_match:
        return _resolve_clock_candidate(
            local_now, tz, int(h24_match.group(1)), int(h24_match.group(2)), is_tomorrow
        )

    named_hours: tuple[tuple[str, int], ...] = (
        ("tonight", 21),
        ("this evening", 18),
        ("evening", 18),
        ("afternoon", 14),
        ("morning", 8),
    )
    for phrase, hr in named_hours:
        if phrase in lowered:
            return _resolve_clock_candidate(local_now, tz, hr, 0, is_tomorrow)

    return None


def parse_duration_minutes(message: str) -> int | None:
    """Parse duration expressions such as '40 min', '1.5 hrs', 'half an hour'."""
    lowered = message.lower()
    if "half an hour" in lowered or "half hour" in lowered:
        return 30
    if "an hour" in lowered:
        return 60
    # Avoid matching "in 2 hours" as a duration
    cleaned = _TIME_IN_RE.sub("", message)
    match = _DURATION_RE.search(cleaned)
    if not match:
        return None
    val = float(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("h"):
        return max(1, round(val * 60))
    return max(1, round(val))


def parse_mode(message: str) -> Mode | None:
    """Extract travel mode from message text."""
    for pat, mode in _MODE_PATTERNS:
        if pat.search(message):
            return mode
    return None


def parse_activity(message: str) -> str | None:
    """Extract outdoor activity from message text."""
    for pat, act in _ACTIVITY_PATTERNS:
        if pat.search(message):
            return act
    return None


def parse_sensitive_hints(message: str) -> list[SensitiveGroup]:
    """Detect sensitive group hints mentioned in the user message."""
    hints: list[SensitiveGroup] = []
    for pat, group in _SENSITIVE_PATTERNS:
        if pat.search(message) and group not in hints:
            hints.append(group)
    return hints


def parse_places(message: str) -> tuple[str | None, str | None]:
    """Extract (origin_text, destination_text) from 'from A to B' or 'to B'."""
    m_both = _FROM_TO_RE.search(message)
    if m_both:
        return m_both.group(1).strip(" ,."), m_both.group(2).strip(" ,.")

    # Do not extract 'to' inside 'how to report', 'best time to jog', 'want to know'
    if _REPORT_HELP_RE.search(message) or _BEST_TIME_RE.search(message):
        return None, None

    m_dest = _TO_PLACE_RE.search(message)
    if m_dest:
        dest = m_dest.group(1).strip(" ,.")
        # Filter out non-place verbs like "jog", "walk", "run", "report"
        if dest.lower() not in {"jog", "run", "walk", "cycle", "report", "go", "know", "do"}:
            return None, dest
    return None, None


def parse_glossary_topic(message: str) -> str | None:
    """Extract glossary term key for explain intent."""
    for pat, key in _GLOSSARY_KEYWORDS:
        if pat.search(message):
            return key
    return None


def classify_intent(
    message: str,
    *,
    origin_text: str | None,
    destination_text: str | None,
    activity: str | None,
    topic: str | None,
) -> Intent:
    """Classify user message into one of the Section 8.14 intents."""
    safety = detect_safety_intent(message)
    if safety is not None:
        return safety
    if _GREETING_RE.match(message):
        return Intent.GREETING
    if _REPORT_HELP_RE.search(message):
        return Intent.REPORT_HELP
    if _REPORTS_NEARBY_RE.search(message):
        return Intent.REPORTS_NEARBY
    if destination_text or origin_text or _ROUTE_HINT_RE.search(message):
        return Intent.ROUTE_COMPARE
    if _HOME_RE.search(message):
        return Intent.HOME_TIPS
    if _BEST_TIME_RE.search(message) and activity is None:
        return Intent.BEST_TIME
    if topic is not None and (_EXPLAIN_RE.search(message) or len(message.split()) <= 5):
        return Intent.EXPLAIN
    if activity is not None:
        return Intent.ACTIVITY_ADVICE
    return Intent.BEST_TIME if _BEST_TIME_RE.search(message) else Intent.AIR_NOW


def parse_message(
    message: str,
    context: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
    tz_name: str = "Asia/Kolkata",
) -> ParsedMessage:
    """Parse message and merge with UI context (message takes precedence)."""
    ctx = context or {}
    ref_now = now or datetime.now(UTC)

    msg_time = parse_time_expression(message, ref_now, tz_name=tz_name)
    msg_dur = parse_duration_minutes(message)
    msg_mode = parse_mode(message)
    msg_act = parse_activity(message)
    orig_text, dest_text = parse_places(message)
    topic = parse_glossary_topic(message)
    hints = parse_sensitive_hints(message)

    intent = classify_intent(
        message,
        origin_text=orig_text,
        destination_text=dest_text,
        activity=msg_act,
        topic=topic,
    )

    # Merge with UI context: message values win over context values
    resolved_time = msg_time
    if resolved_time is None and ctx.get("departure_time"):
        try:
            resolved_time = datetime.fromisoformat(str(ctx["departure_time"]))
        except ValueError:
            resolved_time = None

    resolved_dur = msg_dur if msg_dur is not None else ctx.get("duration_min")
    resolved_mode = msg_mode
    if resolved_mode is None and ctx.get("mode"):
        try:
            resolved_mode = Mode(str(ctx["mode"]))
        except ValueError:
            resolved_mode = None

    resolved_act = msg_act or (str(ctx["activity"]) if ctx.get("activity") else None)

    return ParsedMessage(
        intent=intent,
        departure_time=resolved_time,
        duration_min=int(resolved_dur) if resolved_dur is not None else None,
        mode=resolved_mode,
        activity=resolved_act,
        origin_text=orig_text,
        destination_text=dest_text,
        topic=topic,
        sensitive_hints=hints,
        is_time_budget=msg_dur is not None,
    )
