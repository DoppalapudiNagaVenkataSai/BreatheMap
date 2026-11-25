"""Mode ranking, normalisation, tie marking, and practicality flag detection."""

from app.constants import (
    MAX_CYCLE_DISTANCE_KM,
    MAX_WALK_DISTANCE_KM,
    MAX_WALK_DURATION_MIN,
    TIE_DIFFERENCE_PCT,
)
from app.domain.models import Mode, ModeResult, SortOption


def rank_modes(
    options: list[ModeResult],
    sort_by: SortOption = SortOption.LEAST_POLLUTION,
    prefer_lit: bool = False,
) -> list[ModeResult]:
    """Sort mode comparison results and assign best/about-same markers."""
    if not options:
        return []

    available = [opt for opt in options if opt.status == "available"]
    unavailable = [opt for opt in options if opt.status != "available"]

    if not available:
        return unavailable

    # Mark flags
    for opt in available:
        opt.flags = get_practicality_flags(opt)

    # Normalization min/max for balanced sort
    doses = [opt.dose_ug for opt in available]
    durations = [opt.duration_min for opt in available]

    min_d, max_d = min(doses), max(doses)
    min_t, max_t = min(durations), max(durations)

    def balanced_score(opt: ModeResult) -> float:
        # min-max normalisation: 0 if all equal
        norm_dose = (opt.dose_ug - min_d) / (max_d - min_d) if max_d > min_d else 0.0
        norm_time = (opt.duration_min - min_t) / (max_t - min_t) if max_t > min_t else 0.0
        score = 0.6 * norm_dose + 0.4 * norm_time

        if prefer_lit and opt.lighting:
            # Add lighting penalty: 0.3 * unlit_fraction
            score += 0.3 * (opt.lighting.unlit_pct / 100.0)
        return score

    if sort_by == SortOption.FASTEST:
        available.sort(key=lambda o: o.duration_min)
    elif sort_by == SortOption.BALANCED:
        available.sort(key=balanced_score)
    else:  # SortOption.LEAST_POLLUTION
        available.sort(key=lambda o: o.dose_ug)

    # Compute best option by lowest dose
    best_dose = min(doses)
    for opt in available:
        if best_dose > 0:
            diff_pct = ((opt.dose_ug - best_dose) / best_dose) * 100.0
            opt.pct_vs_best = round(diff_pct, 1)
            opt.is_best = opt.dose_ug == best_dose
            opt.is_about_same = diff_pct <= TIE_DIFFERENCE_PCT and not opt.is_best
        else:
            opt.pct_vs_best = 0.0
            opt.is_best = True
            opt.is_about_same = False

    return available + unavailable


def get_practicality_flags(option: ModeResult) -> list[str]:
    """Detect usability and comfort flags."""
    flags: list[str] = []
    if option.mode == Mode.WALK:
        if option.duration_min > MAX_WALK_DURATION_MIN or option.distance_km > MAX_WALK_DISTANCE_KM:
            flags.append("Long walk")
    elif option.mode == Mode.CYCLE and option.distance_km > MAX_CYCLE_DISTANCE_KM:
        flags.append("Long ride")
    return flags
