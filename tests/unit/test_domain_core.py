"""Comprehensive test suite for pure domain logic."""

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.advice import advise
from app.domain.aqi import naqi, sub_index, us_level
from app.domain.exposure import (
    AirPoint,
    Segment,
    estimate_dose,
)
from app.domain.geo import (
    geohash_decode_bbox,
    geohash_encode,
    geohash_neighbors,
    haversine_m,
    line_midpoint,
    point_to_segment_distance_m,
    resample_line,
    simplify_line,
)
from app.domain.home_tips import HomeTip, select_tips
from app.domain.lighting import summarize_lighting
from app.domain.models import Activity, Level, Mode, ModeResult, SensitiveGroup, SortOption
from app.domain.modes import emissions_kg, estimate_auto, estimate_bus, estimate_metro
from app.domain.ranking import rank_modes
from app.domain.timeutils import is_night, rolling_mean, round_to_bucket, to_local, value_at
from app.domain.windows import cleanest_and_worst, optimize_departure


def test_domain_purity_no_framework_or_network_imports() -> None:
    """Verify that app/domain has ZERO imports of httpx, fastapi, or google.*."""
    domain_dir = Path("app/domain")
    forbidden = ["httpx", "fastapi", "google", "starlette"]

    for py_file in domain_dir.glob("*.py"):
        with open(py_file, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    for forb in forbidden:
                        assert not name.name.startswith(forb), (
                            f"Forbidden import {name.name} in {py_file}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                for forb in forbidden:
                    assert not node.module.startswith(forb), (
                        f"Forbidden import from {node.module} in {py_file}"
                    )


def test_geo_utilities() -> None:
    # 1. Haversine
    dist = haversine_m(28.6139, 77.2090, 28.6289, 77.2065)
    assert 1500.0 < dist < 1800.0

    # 2. Geohash
    gh = geohash_encode(28.6139, 77.2090, precision=5)
    assert len(gh) == 5
    bbox = geohash_decode_bbox(gh)
    assert bbox[0] <= 28.6139 <= bbox[2]
    assert bbox[1] <= 77.2090 <= bbox[3]

    neighbors = geohash_neighbors(gh)
    assert len(neighbors) == 8

    # 3. Resample line & simplify
    coords = [(28.6, 77.2), (28.61, 77.2), (28.62, 77.2)]
    resampled = resample_line(coords, step_m=200.0)
    assert len(resampled) > len(coords)
    simplified = simplify_line(resampled, max_points=10)
    assert len(simplified) <= 10

    # 4. Midpoint
    mid = line_midpoint(coords)
    assert pytest.approx(mid[0], rel=1e-2) == 28.61
    assert pytest.approx(mid[1], rel=1e-2) == 77.2

    # 5. Point to segment
    p_dist = point_to_segment_distance_m(28.605, 77.201, 28.60, 77.20, 28.61, 77.20)
    assert p_dist > 0.0


def test_timeutils() -> None:
    # Rolling mean
    vals: list[float | None] = [10.0, 20.0, 30.0, None, 50.0]
    rm = rolling_mean(vals, window=3)
    assert rm[0] == 10.0
    assert rm[1] == 15.0
    assert rm[2] == 20.0

    # Interpolation
    t0 = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 25, 13, 0, tzinfo=UTC)
    t_mid = datetime(2026, 11, 25, 12, 30, tzinfo=UTC)
    interp = value_at([t0, t1], [100.0, 200.0], t_mid)
    assert interp == 150.0

    # Night check
    sr = datetime(2026, 11, 25, 6, 30, tzinfo=UTC)
    ss = datetime(2026, 11, 25, 17, 30, tzinfo=UTC)
    night_trip = datetime(2026, 11, 25, 21, 0, tzinfo=UTC)
    assert is_night(night_trip, night_trip, sr, ss) is True

    # Timezone & Bucket
    local = to_local(t0, "Asia/Kolkata")
    assert local.hour == 17  # UTC 12:00 -> IST 17:30
    bucket = round_to_bucket(datetime(2026, 11, 25, 12, 14), minutes=30)
    assert bucket.minute == 0


def test_aqi_calculations() -> None:
    # Sub index for PM2.5 breakpoints
    assert sub_index("pm25", 0.0) == 0
    assert sub_index("pm25", 30.0) == 50
    assert sub_index("pm25", 60.0) == 100
    assert sub_index("pm25", 90.0) == 200
    assert sub_index("pm25", 120.0) == 300
    assert sub_index("pm25", 250.0) == 400
    assert sub_index("pm25", 380.0) == 500
    assert sub_index("pm25", 600.0) == 500  # Capped at 500

    # NAQI overall
    full_pollutants = {
        "pm25": 45.0,  # sub-index in 51-100
        "pm10": 80.0,  # sub-index in 51-100
        "no2": 30.0,  # sub-index in 0-50
    }
    res = naqi(full_pollutants)
    assert res.status == "ok"
    assert res.level in (Level.L1, Level.L2)

    # Insufficient data (< 3 pollutants)
    insuf = naqi({"pm25": 80.0})
    assert insuf.status == "insufficient_data"

    # US AQI mapping
    assert us_level(45) == Level.L1
    assert us_level(85) == Level.L2
    assert us_level(130) == Level.L3
    assert us_level(180) == Level.L4
    assert us_level(250) == Level.L5
    assert us_level(350) == Level.L6


def test_exposure_dose_hand_computed() -> None:
    # 2 segments walk, 0.1 h each, C = 100 and 200 µg/m³, F_mode = 1.0, F_road = 1.0, V = 1.3
    # Expected dose = (100 * 0.1 + 200 * 0.1) * 1.3 = 30 * 1.3 = 39.0 µg
    # Average experienced PM2.5 = (100 * 0.1 + 200 * 0.1) / 0.2 = 150.0 µg/m³
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    later = datetime(2026, 11, 25, 11, 0, tzinfo=UTC)
    ap = AirPoint(coord=(28.6, 77.2), times=[now, later], values=[150.0, 150.0])

    # Each segment duration is 0.1 h, concentration 150, F_mode 1.0, V 1.3
    # seg1 dose = 150 * 1.3 * 0.1 = 19.5 µg
    # 1 segment gives 19.5; 2 segments gives 39.0 if total duration_h is 0.2 (0.1 each)
    seg1 = Segment(
        start=(28.6, 77.2),
        end=(28.601, 77.2),
        midpoint=(28.6, 77.2),
        distance_m=100.0,
        duration_h=0.1,
        elapsed_start_h=0.0,
        waytype="unknown",
    )
    seg2 = Segment(
        start=(28.601, 77.2),
        end=(28.602, 77.2),
        midpoint=(28.6, 77.2),
        distance_m=100.0,
        duration_h=0.1,
        elapsed_start_h=0.1,
        waytype="unknown",
    )

    dose, avg_pm = estimate_dose([seg1], v_mode=1.3, f_mode=1.0, air_points=[ap], start_time=now)
    assert pytest.approx(dose, abs=0.1) == 19.5
    assert pytest.approx(avg_pm, abs=0.1) == 150.0

    two_seg_dose, _ = estimate_dose(
        [seg1, seg2], v_mode=1.3, f_mode=1.0, air_points=[ap], start_time=now
    )
    assert pytest.approx(two_seg_dose, abs=0.1) == 39.0


def test_modes_and_emissions() -> None:
    car = ModeResult(
        mode=Mode.CAR,
        is_estimated=False,
        duration_min=20.0,
        distance_km=10.0,
        dose_ug=50.0,
        avg_pm25=120.0,
    )
    auto = estimate_auto(car)
    assert auto.mode == Mode.AUTO
    assert auto.duration_min == 22.0  # 20 * 1.1
    assert auto.dose_ug > car.dose_ug

    bus = estimate_bus(car, avg_ambient_pm25=150.0)
    assert bus.mode == Mode.BUS
    assert bus.duration_min == 40.0  # 20 * 1.6 + 8

    # Metro
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    ap = AirPoint(coord=(28.6, 77.2), times=[now], values=[100.0])
    metro = estimate_metro((28.6, 77.2), (28.7, 77.3), [ap], now)
    assert metro.mode == Mode.METRO
    assert metro.duration_min > 0

    assert emissions_kg(Mode.CAR, 10.0) == 1.70
    assert emissions_kg(Mode.WALK, 10.0) == 0.0


def test_windows_and_departure_optimizer() -> None:
    times = [datetime(2026, 11, 25, h, 0, tzinfo=UTC) for h in range(10)]
    vals = [100.0, 90.0, 80.0, 50.0, 40.0, 30.0, 150.0, 200.0, 250.0, 300.0]

    cleanest, worst = cleanest_and_worst(times, vals, window_h=3)
    assert cleanest is not None and worst is not None
    assert cleanest.avg_pm25 == 40.0  # (50 + 40 + 30) / 3
    assert worst.avg_pm25 == 250.0  # (200 + 250 + 300) / 3

    # Optimize departure: threshold 15%
    def dummy_eval(t: datetime) -> float:
        # Time 12:00 has dose 100, 13:00 has dose 60 (40% reduction)
        return 60.0 if t.hour == 13 else 100.0

    t_req = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    opt = optimize_departure(dummy_eval, t_req, flexibility_min=60, step_min=30)
    assert opt is not None
    assert opt[0].hour == 13
    assert opt[2] == 40.0


def test_lighting_and_ranking() -> None:
    seg = Segment(
        start=(28.6, 77.2),
        end=(28.601, 77.2),
        midpoint=(28.6005, 77.2),
        distance_m=100.0,
        duration_h=0.05,
        elapsed_start_h=0.0,
        waytype="street",
    )
    way_lit = {"lit": "yes", "coords": [(28.6, 77.2), (28.601, 77.2)]}
    summary = summarize_lighting([seg], [way_lit])
    assert summary.lit_pct == 100.0
    assert summary.unlit_pct == 0.0

    # Ranking
    m1 = ModeResult(
        mode=Mode.WALK,
        is_estimated=False,
        duration_min=40,
        distance_km=3,
        dose_ug=100,
        avg_pm25=100,
    )
    m2 = ModeResult(
        mode=Mode.CYCLE,
        is_estimated=False,
        duration_min=15,
        distance_km=3,
        dose_ug=105,
        avg_pm25=100,
    )
    ranked = rank_modes([m1, m2], sort_by=SortOption.LEAST_POLLUTION)
    assert ranked[0].mode == Mode.WALK
    assert ranked[1].is_about_same is True  # 105 is within 10% of 100


def test_advice_and_home_tips() -> None:
    adv = advise(Level.L3, Activity.JOG)
    assert "Higher-intensity" in adv.advice

    adv_sensitive = advise(Level.L3, Activity.WALK, [SensitiveGroup.CHILD])
    assert adv_sensitive.level == Level.L4  # Shifted to L4
    assert adv_sensitive.cautious_note is not None

    # Sensitive shift capped at L6
    adv_severe = advise(Level.L6, Activity.WALK, [SensitiveGroup.ASTHMA])
    assert adv_severe.level == Level.L6

    tips = [
        HomeTip(
            id="t1",
            title="Free Tip",
            text="...",
            applies_min_level=Level.L2,
            mechanism="...",
            cost="free",
        ),
        HomeTip(
            id="t2",
            title="Paid Tip",
            text="...",
            applies_min_level=Level.L2,
            mechanism="...",
            cost="low",
        ),
    ]
    selected = select_tips(tips, Level.L3)
    assert len(selected) == 2
    assert selected[0].cost == "free"
