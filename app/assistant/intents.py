"""Assistant intent definitions, required slot ordering, and tool mappings."""

from enum import StrEnum


class Intent(StrEnum):
    """Supported assistant intents (Section 8.14)."""

    AIR_NOW = "air_now"
    BEST_TIME = "best_time"
    ACTIVITY_ADVICE = "activity_advice"
    ROUTE_COMPARE = "route_compare"
    HOME_TIPS = "home_tips"
    REPORTS_NEARBY = "reports_nearby"
    REPORT_HELP = "report_help"
    EXPLAIN = "explain"
    GREETING = "greeting"
    OUT_OF_SCOPE = "out_of_scope"
    EMERGENCY = "emergency"
    MEDICAL = "medical"


INTENT_REQUIRED_SLOTS: dict[Intent, tuple[str, ...]] = {
    Intent.AIR_NOW: ("location",),
    Intent.BEST_TIME: ("location",),
    Intent.ACTIVITY_ADVICE: ("location", "time", "duration", "activity"),
    Intent.ROUTE_COMPARE: ("origin", "destination", "departure_time", "mode", "activity"),
    Intent.HOME_TIPS: ("location",),
    Intent.REPORTS_NEARBY: ("location",),
    Intent.REPORT_HELP: ("location",),
    Intent.EXPLAIN: (),
    Intent.GREETING: (),
    Intent.OUT_OF_SCOPE: (),
    Intent.EMERGENCY: (),
    Intent.MEDICAL: (),
}

INTENT_TOOLS: dict[Intent, tuple[str, ...]] = {
    Intent.AIR_NOW: ("air",),
    Intent.BEST_TIME: ("air", "windows"),
    Intent.ACTIVITY_ADVICE: ("air", "activity_window", "advice", "sensitive"),
    Intent.ROUTE_COMPARE: ("routes", "windows", "lighting", "reports"),
    Intent.HOME_TIPS: ("air", "home_tips"),
    Intent.REPORTS_NEARBY: ("reports",),
    Intent.REPORT_HELP: ("report_link",),
    Intent.EXPLAIN: ("glossary",),
    Intent.GREETING: (),
    Intent.OUT_OF_SCOPE: (),
    Intent.EMERGENCY: (),
    Intent.MEDICAL: (),
}

STATIC_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.GREETING,
        Intent.OUT_OF_SCOPE,
        Intent.EMERGENCY,
        Intent.MEDICAL,
        Intent.REPORT_HELP,
    }
)
