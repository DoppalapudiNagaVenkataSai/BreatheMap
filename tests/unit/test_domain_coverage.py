"""Additional unit tests to ensure domain coverage exceeds 95%."""

from datetime import UTC, datetime
from pathlib import Path

from app.domain.aqi import band_name, level_for, sub_index
from app.domain.exposure import Segment, segment_route
from app.domain.home_tips import load_tips
from app.domain.lighting import summarize_lighting
from app.domain.models import Level, Mode, ModeResult, Scale, SortOption
from app.domain.ranking import rank_modes
from app.domain.windows import cleanest_and_worst, optimize_departure


def test_segment_route_empty_and_full() -> None:
    assert segment_route([], duration_s=100) == []
    coords = [(28.6, 77.2), (28.61, 77.21)]
    segs = segment_route(coords, duration_s=600, waytypes=["street"])
    assert len(segs) >= 1
    assert segs[0].waytype == "street"


def test_home_tips_load_file() -> None:
    tips_file = Path("data/knowledge/home_tips.json")
    tips = load_tips(tips_file)
    assert len(tips) > 0
    assert tips[0].id is not None
    assert load_tips("non_existent_file.json") == []


def test_aqi_sub_index_boundary_cases() -> None:
    assert sub_index("pm10", -5.0) is None
    assert sub_index("unknown_pollutant", 50.0) is None
    # Test all pollutants in NAQI table
    for pol in ["pm10", "pm25", "no2", "o3", "co", "so2"]:
        assert sub_index(pol, 10.0) is not None

    # Test band names for both scales
    for lvl in [Level.L1, Level.L2, Level.L3, Level.L4, Level.L5, Level.L6]:
        assert band_name(Scale.NAQI, lvl) != ""
        assert band_name(Scale.US, lvl) != ""

    # Test level_for scale
    assert level_for(Scale.NAQI, 25) == Level.L1
    assert level_for(Scale.NAQI, 75) == Level.L2
    assert level_for(Scale.NAQI, 150) == Level.L3
    assert level_for(Scale.NAQI, 250) == Level.L4
    assert level_for(Scale.NAQI, 350) == Level.L5
    assert level_for(Scale.NAQI, 450) == Level.L6


def test_ranking_fastest_balanced_and_unavailable() -> None:
    m1 = ModeResult(
        mode=Mode.WALK,
        is_estimated=False,
        duration_min=40,
        distance_km=3,
        dose_ug=100,
        avg_pm25=100,
    )
    m2 = ModeResult(
        mode=Mode.CAR, is_estimated=False, duration_min=10, distance_km=3, dose_ug=120, avg_pm25=100
    )
    unavail = ModeResult(
        mode=Mode.METRO,
        is_estimated=True,
        duration_min=0,
        distance_km=0,
        dose_ug=0,
        avg_pm25=0,
        status="unavailable",
    )

    fastest = rank_modes([m1, m2, unavail], sort_by=SortOption.FASTEST)
    assert fastest[0].mode == Mode.CAR
    assert fastest[-1].status == "unavailable"

    balanced = rank_modes([m1, m2], sort_by=SortOption.BALANCED, prefer_lit=True)
    assert len(balanced) == 2


def test_lighting_empty_and_unlit() -> None:
    assert summarize_lighting([], []).coverage_pct == 0.0
    seg = Segment(
        start=(28.6, 77.2),
        end=(28.601, 77.2),
        midpoint=(28.6005, 77.2),
        distance_m=100.0,
        duration_h=0.05,
        elapsed_start_h=0.0,
        waytype="street",
    )
    way_unlit = {"lit": "no", "coords": [(28.6, 77.2), (28.601, 77.2)]}
    sum_unlit = summarize_lighting([seg], [way_unlit])
    assert sum_unlit.unlit_pct == 100.0


def test_windows_edge_cases() -> None:
    # Insufficient length
    c, w = cleanest_and_worst([], [])
    assert c is None and w is None

    # Optimize departure zero dose
    opt = optimize_departure(lambda t: 0.0, datetime.now(tz=UTC), flexibility_min=30)
    assert opt is None
