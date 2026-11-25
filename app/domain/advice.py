"""Activity advice rules with sensitive-group escalation."""

from app.domain.models import Activity, Advice, Level, SensitiveGroup

LEVEL_ORDER = [Level.L1, Level.L2, Level.L3, Level.L4, Level.L5, Level.L6]


def advise(
    level: Level,
    activity: Activity,
    sensitive_groups: list[SensitiveGroup] | None = None,
) -> Advice:
    """Generate activity recommendation based on AQI level and user context."""
    effective_level = level
    cautious_note: str | None = None

    if sensitive_groups:
        idx = LEVEL_ORDER.index(level)
        # Shift one level more cautious, capped at L6
        new_idx = min(idx + 1, len(LEVEL_ORDER) - 1)
        effective_level = LEVEL_ORDER[new_idx]
        group_names = ", ".join(g.value for g in sensitive_groups)
        cautious_note = f"Because you selected {group_names}, recommendations are more cautious."

    summary = f"Advice for {activity.value.capitalize()} at {effective_level.value}"

    if effective_level in (Level.L1, Level.L2):
        text = "Conditions are relatively good for this activity."
    elif effective_level == Level.L3:
        text = "Fine for most people; consider a shorter or lighter session."
    elif effective_level == Level.L4:
        text = "Shorten the session or move it to the cleanest window; consider indoors."
    elif effective_level == Level.L5:
        text = "Avoid strenuous outdoor activity; choose the cleanest window or go indoors."
    else:  # Level.L6
        text = "Avoid outdoor exertion; an indoor alternative is recommended."

    if activity in (Activity.JOG, Activity.CYCLE) and effective_level in (
        Level.L3,
        Level.L4,
        Level.L5,
        Level.L6,
    ):
        text += " Higher-intensity activities make you breathe in more."

    return Advice(
        level=effective_level,
        summary=summary,
        advice=text,
        cautious_note=cautious_note,
    )
