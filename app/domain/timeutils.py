"""Time, rolling mean, and timezone interpolation utilities."""

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo


def rolling_mean(values: list[float | None], window: int) -> list[float | None]:
    """Compute rolling mean over a moving window of past hours."""
    means: list[float | None] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        sub = [v for v in values[start : i + 1] if v is not None]
        # Require at least 50% data availability for valid window mean
        if len(sub) >= max(1, window // 2):
            means.append(sum(sub) / len(sub))
        else:
            means.append(None)
    return means


def value_at(
    times: list[datetime], values: list[float | None], target_time: datetime
) -> float | None:
    """Linear interpolation of a value at a target datetime."""
    if not times or not values or len(times) != len(values):
        return None

    # Normalize target_time to UTC
    target_utc = target_time.astimezone(UTC)
    utc_times = [t.astimezone(UTC) for t in times]

    if target_utc < utc_times[0] or target_utc > utc_times[-1]:
        return None

    for i in range(len(utc_times) - 1):
        t1, t2 = utc_times[i], utc_times[i + 1]
        if t1 <= target_utc <= t2:
            v1, v2 = values[i], values[i + 1]
            if v1 is None or v2 is None:
                return v1 if v1 is not None else v2
            span = (t2 - t1).total_seconds()
            if span == 0:
                return v1
            factor = (target_utc - t1).total_seconds() / span
            return v1 + factor * (v2 - v1)

    return values[-1]


def is_night(start: datetime, end: datetime, sunrise: datetime, sunset: datetime) -> bool:
    """Determine if a trip time overlaps with night hours (sunset to sunrise)."""
    # Normalize to UTC
    s = start.astimezone(UTC)
    e = end.astimezone(UTC)
    sr = sunrise.astimezone(UTC)
    ss = sunset.astimezone(UTC)

    # Night is between sunset and sunrise
    # If sunset > sunrise (same day), night is before sunrise or after sunset
    if ss > sr:
        return (s < sr or s > ss) or (e < sr or e > ss)
    else:
        return (s >= ss and s <= sr) or (e >= ss and e <= sr)


def to_local(dt: datetime, tz_name: str) -> datetime:
    """Convert UTC datetime to location local timezone."""
    tz: tzinfo
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    return dt.astimezone(tz)


def round_to_bucket(dt: datetime, minutes: int = 30) -> datetime:
    """Round datetime to the nearest minute bucket."""
    discard = timedelta(
        minutes=dt.minute % minutes,
        seconds=dt.second,
        microseconds=dt.microsecond,
    )
    dt -= discard
    if discard >= timedelta(minutes=minutes / 2):
        dt += timedelta(minutes=minutes)
    return dt
