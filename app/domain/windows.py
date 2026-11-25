"""Time window evaluation, departure optimization, and activity windows."""

from collections.abc import Callable
from datetime import datetime, timedelta

from app.constants import DEPARTURE_OPTIMIZE_THRESHOLD_PCT
from app.domain.models import Window


def cleanest_and_worst(
    times: list[datetime],
    values: list[float | None],
    window_h: int = 3,
    horizon_h: int = 24,
) -> tuple[Window | None, Window | None]:
    """Find the cleanest and worst consecutive 3-hour windows within horizon."""
    if len(times) < window_h or len(values) < window_h:
        return None, None

    valid_windows: list[Window] = []
    limit = min(len(times) - window_h + 1, horizon_h)

    for i in range(limit):
        sub_vals = [v for v in values[i : i + window_h] if v is not None]
        if len(sub_vals) == window_h:
            avg = sum(sub_vals) / len(sub_vals)
            valid_windows.append(
                Window(
                    start_time=times[i],
                    end_time=times[i + window_h - 1],
                    avg_pm25=round(avg, 1),
                    label="",
                )
            )

    if not valid_windows:
        return None, None

    cleanest = min(valid_windows, key=lambda w: w.avg_pm25)
    worst = max(valid_windows, key=lambda w: w.avg_pm25)

    cleanest.label = "Cleanest window"
    worst.label = "Worst window"

    return cleanest, worst


def optimize_departure(
    eval_fn: Callable[[datetime], float],
    requested_time: datetime,
    flexibility_min: int,
    step_min: int = 30,
) -> tuple[datetime, float, float] | None:
    """Evaluate candidate departure times across flexibility window.

    Returns (best_time, best_dose, reduction_pct) if reduction >= 15%, else None.
    """
    if flexibility_min <= 0:
        return None

    base_dose = eval_fn(requested_time)
    if base_dose <= 0:
        return None

    best_time = requested_time
    best_dose = base_dose

    steps = flexibility_min // step_min
    for i in range(-steps, steps + 1):
        if i == 0:
            continue
        candidate_time = requested_time + timedelta(minutes=i * step_min)
        dose = eval_fn(candidate_time)
        if dose < best_dose:
            best_dose = dose
            best_time = candidate_time

    reduction_pct = ((base_dose - best_dose) / base_dose) * 100.0
    if reduction_pct >= DEPARTURE_OPTIMIZE_THRESHOLD_PCT:
        return best_time, round(best_dose, 1), round(reduction_pct, 1)

    return None
