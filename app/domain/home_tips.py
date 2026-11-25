"""Indoor home exposure tips filtering and ranking."""

import json
from pathlib import Path

from app.domain.models import HomeTip, Level

LEVEL_ORDER = [Level.L1, Level.L2, Level.L3, Level.L4, Level.L5, Level.L6]


def load_tips(path: Path | str) -> list[HomeTip]:
    """Load and parse home tips from JSON storage."""
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return [HomeTip(**item) for item in data]


def select_tips(
    tips: list[HomeTip],
    level: Level,
    limit: int = 5,
) -> list[HomeTip]:
    """Select appropriate tips for current AQI level, prioritizing zero-cost actions."""
    current_idx = LEVEL_ORDER.index(level)
    matching = [tip for tip in tips if LEVEL_ORDER.index(tip.applies_min_level) <= current_idx]
    # Rank free first, then low cost
    matching.sort(key=lambda t: 0 if t.cost == "free" else 1)
    return matching[:limit]
