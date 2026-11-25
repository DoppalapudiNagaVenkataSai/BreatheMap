"""Exposure model: route segmentation, spatial/temporal IDW, and inhaled dose calculation."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.constants import ROAD_FACTORS
from app.domain.geo import haversine_m, resample_line
from app.domain.timeutils import value_at


@dataclass
class Segment:
    """Individual route segment."""

    start: tuple[float, float]
    end: tuple[float, float]
    midpoint: tuple[float, float]
    distance_m: float
    duration_h: float
    elapsed_start_h: float
    waytype: str


@dataclass
class AirPoint:
    """Air forecast series at a geographic point."""

    coord: tuple[float, float]
    times: list[datetime]
    values: list[float | None]


def segment_route(
    coordinates: list[tuple[float, float]],
    duration_s: float,
    waytypes: list[str] | None = None,
    step_m: float = 200.0,
) -> list[Segment]:
    """Resample route into uniform segments and partition total duration proportionally."""
    resampled = resample_line(coordinates, step_m=step_m)
    if len(resampled) < 2:
        return []

    # Calculate individual segment distances
    seg_dists: list[float] = []
    for i in range(len(resampled) - 1):
        dist = haversine_m(
            resampled[i][0], resampled[i][1], resampled[i + 1][0], resampled[i + 1][1]
        )
        seg_dists.append(max(1.0, dist))

    total_dist = sum(seg_dists)
    total_hours = duration_s / 3600.0

    segments: list[Segment] = []
    elapsed_h = 0.0

    for i in range(len(resampled) - 1):
        d_m = seg_dists[i]
        seg_h = (d_m / total_dist) * total_hours if total_dist > 0 else 0.0
        p1 = resampled[i]
        p2 = resampled[i + 1]
        mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)

        # Map waytype from input or default to unknown
        wtype = "unknown"
        if waytypes and i < len(waytypes):
            wtype = waytypes[i]

        segments.append(
            Segment(
                start=p1,
                end=p2,
                midpoint=mid,
                distance_m=d_m,
                duration_h=seg_h,
                elapsed_start_h=elapsed_h,
                waytype=wtype,
            )
        )
        elapsed_h += seg_h

    return segments


def concentration_at_point(
    pt: tuple[float, float],
    air_points: list[AirPoint],
    target_time: datetime,
) -> float:
    """Inverse Distance Weighting (IDW) interpolation across spatial air points and time."""
    if not air_points:
        return 0.0

    # Get temporal concentration at each air point
    point_concs = [value_at(ap.times, ap.values, target_time) for ap in air_points]

    weights: list[float] = []
    values: list[float] = []

    for i, ap in enumerate(air_points):
        val = point_concs[i]
        if val is None:
            continue
        dist = haversine_m(pt[0], pt[1], ap.coord[0], ap.coord[1])
        if dist < 1.0:  # Coinciding location
            return val
        w = 1.0 / (dist * dist)
        weights.append(w)
        values.append(val)

    if not weights:
        # Fallback to mean or zero
        valid = [v for v in point_concs if v is not None]
        return sum(valid) / len(valid) if valid else 0.0

    total_w = sum(weights)
    return sum(w * v for w, v in zip(weights, values, strict=False)) / total_w


def estimate_dose(
    segments: list[Segment],
    v_mode: float,
    f_mode: float,
    air_points: list[AirPoint],
    start_time: datetime,
) -> tuple[float, float]:
    """Calculate comparative PM2.5 dose (µg) and average experienced PM2.5 (µg/m³).

    Dose (µg) = Σ C_i(t_i) × F_mode × F_road,i × V_mode × Δt_i
    Avg Experienced = Σ C_i(t_i) × F_mode × F_road,i × Δt_i / Σ Δt_i
    """
    if not segments:
        return 0.0, 0.0

    total_dose = 0.0
    weighted_conc_sum = 0.0
    total_duration_h = 0.0

    for seg in segments:
        seg_time = start_time + timedelta(hours=seg.elapsed_start_h)
        c_ambient = concentration_at_point(seg.midpoint, air_points, seg_time)
        f_road = ROAD_FACTORS.get(seg.waytype.lower(), 1.0)

        experienced_c = c_ambient * f_mode * f_road
        seg_dose = experienced_c * v_mode * seg.duration_h

        total_dose += seg_dose
        weighted_conc_sum += experienced_c * seg.duration_h
        total_duration_h += seg.duration_h

    avg_pm25 = weighted_conc_sum / total_duration_h if total_duration_h > 0 else 0.0
    return round(total_dose, 1), round(avg_pm25, 1)
