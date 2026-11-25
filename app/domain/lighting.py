"""Street lighting analysis for night trips."""

from app.domain.exposure import Segment
from app.domain.geo import point_to_segment_distance_m
from app.domain.models import LightingSummary


def _classify_way_lit(lit_val: str) -> str:
    if lit_val in ("yes", "24/7", "automatic"):
        return "lit"
    if lit_val in ("no", "disused"):
        return "unlit"
    return "unknown"


def _find_nearest_way_lit(
    midpoint: tuple[float, float],
    ways: list[dict[str, object]],
    max_dist_m: float,
) -> str:
    seg_lit = "unknown"
    min_d = float("inf")

    for way in ways:
        lit_tag = str(way.get("lit", "")).lower()
        coords = way.get("coords")
        if not isinstance(coords, list) or len(coords) < 2:
            continue

        for k in range(len(coords) - 1):
            p1, p2 = coords[k], coords[k + 1]
            dist = point_to_segment_distance_m(midpoint[0], midpoint[1], p1[0], p1[1], p2[0], p2[1])
            if dist < min_d and dist <= max_dist_m:
                min_d = dist
                seg_lit = _classify_way_lit(lit_tag)

    return seg_lit


def summarize_lighting(
    segments: list[Segment],
    ways_with_lit: list[dict[str, object]],
    max_dist_m: float = 25.0,
) -> LightingSummary:
    """Classify segments into lit, unlit, or unknown based on OSM ways within 25 m."""
    if not segments:
        return LightingSummary(
            lit_pct=0.0,
            unlit_pct=0.0,
            unknown_pct=100.0,
            coverage_pct=0.0,
            description="No route segments available",
        )

    lit_len = 0.0
    unlit_len = 0.0
    unknown_len = 0.0
    total_len = sum(s.distance_m for s in segments) or 1.0

    for seg in segments:
        seg_lit = _find_nearest_way_lit(seg.midpoint, ways_with_lit, max_dist_m)
        if seg_lit == "lit":
            lit_len += seg.distance_m
        elif seg_lit == "unlit":
            unlit_len += seg.distance_m
        else:
            unknown_len += seg.distance_m

    lit_pct = round((lit_len / total_len) * 100.0, 1)
    unlit_pct = round((unlit_len / total_len) * 100.0, 1)
    unknown_pct = round((unknown_len / total_len) * 100.0, 1)
    coverage_pct = round(100.0 - unknown_pct, 1)
    desc = f"Lit {lit_pct}% · Unlit {unlit_pct}% · Unknown {unknown_pct}%"

    return LightingSummary(
        lit_pct=lit_pct,
        unlit_pct=unlit_pct,
        unknown_pct=unknown_pct,
        coverage_pct=coverage_pct,
        description=desc,
    )
