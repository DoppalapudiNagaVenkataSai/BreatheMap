"""Unit tests for BreatheWatch ReportService rules (Section 8.13)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import NotFoundError, OutOfRangeError, RateLimitedError, ValidationAppError
from app.services.report_service import ReportService
from app.storage.memory_store import MemoryStore


@pytest.mark.asyncio
async def test_create_report_and_rounding_and_ttl() -> None:
    store = MemoryStore()
    service = ReportService(store)
    now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

    res = await service.create_report(
        category="vehicle_emissions",
        description="  Heavy   smoke\x00 from diesel bus idling at crossing.  ",
        lat=28.63156,
        lon=77.21678,
        user_lat=28.632,
        user_lon=77.217,
        reporter_hash="user1",
        now=now,
    )
    assert res["duplicate_of"] is None
    rep = res["report"]
    assert rep["lat"] == 28.632
    assert rep["lon"] == 77.217
    assert rep["description"] == "Heavy smoke from diesel bus idling at crossing."
    assert rep["status_label"] == "Unverified community report"
    # vehicle_emissions TTL = 6 hours
    assert rep["expires_at"] == (now + timedelta(hours=6)).isoformat()


@pytest.mark.asyncio
async def test_create_report_validation_privacy_and_blocked_words() -> None:
    store = MemoryStore()
    service = ReportService(store)

    # Invalid category
    with pytest.raises(ValidationAppError):
        await service.create_report(
            category="invalid_cat",
            description="Valid description of smoke here.",
            lat=28.63,
            lon=77.22,
            user_lat=28.63,
            user_lon=77.22,
            reporter_hash="u1",
        )

    # Too short
    with pytest.raises(ValidationAppError):
        await service.create_report(
            category="smoke",
            description="Too short",
            lat=28.63,
            lon=77.22,
            user_lat=28.63,
            user_lon=77.22,
            reporter_hash="u1",
        )

    # URL rejected
    with pytest.raises(ValidationAppError, match="URLs"):
        await service.create_report(
            category="smoke",
            description="Check out https://example.com for details",
            lat=28.63,
            lon=77.22,
            user_lat=28.63,
            user_lon=77.22,
            reporter_hash="u1",
        )

    # Email rejected
    with pytest.raises(ValidationAppError, match="email"):
        await service.create_report(
            category="smoke",
            description="Contact me at user@example.com about this smoke",
            lat=28.63,
            lon=77.22,
            user_lat=28.63,
            user_lon=77.22,
            reporter_hash="u1",
        )

    # Phone rejected
    with pytest.raises(ValidationAppError, match="phone"):
        await service.create_report(
            category="smoke",
            description="Call 9876543210 for more info on burning",
            lat=28.63,
            lon=77.22,
            user_lat=28.63,
            user_lon=77.22,
            reporter_hash="u1",
        )

    # Blocked word rejected
    with pytest.raises(ValidationAppError, match="blocked"):
        await service.create_report(
            category="smoke",
            description="This is total spam burning near the gate",
            lat=28.63,
            lon=77.22,
            user_lat=28.63,
            user_lon=77.22,
            reporter_hash="u1",
        )


@pytest.mark.asyncio
async def test_50km_user_distance_rule() -> None:
    store = MemoryStore()
    service = ReportService(store)

    with pytest.raises(OutOfRangeError, match="near your current location"):
        await service.create_report(
            category="smoke",
            description="Thick smoke observed near the highway.",
            lat=29.5,
            lon=77.2,
            user_lat=28.6,
            user_lon=77.2,
            reporter_hash="u1",
        )


@pytest.mark.asyncio
async def test_duplicate_rules_distance_and_category() -> None:
    store = MemoryStore()
    service = ReportService(store)
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)

    first = await service.create_report(
        category="open_burning",
        description="Leaf burning beside the park entrance.",
        lat=28.630,
        lon=77.220,
        user_lat=28.630,
        user_lon=77.220,
        reporter_hash="u1",
        now=now,
    )
    first_id = first["report"]["id"]

    # Same category within ~111 m (0.001 deg lat) and within 2h -> duplicate
    dup = await service.create_report(
        category="open_burning",
        description="Another person seeing the same burning.",
        lat=28.631,
        lon=77.220,
        user_lat=28.631,
        user_lon=77.220,
        reporter_hash="u2",
        now=now + timedelta(minutes=30),
    )
    assert dup["duplicate_of"] == first_id
    assert "I see this too" in dup["message"]

    # Different category at exact same spot -> NOT a duplicate
    diff_cat = await service.create_report(
        category="road_dust",
        description="Heavy dust cloud kicked up by trucks.",
        lat=28.630,
        lon=77.220,
        user_lat=28.630,
        user_lon=77.220,
        reporter_hash="u2",
        now=now + timedelta(minutes=35),
    )
    assert diff_cat["duplicate_of"] is None

    # Same category ~333 m away (0.003 deg lat > 300 m) -> NOT a duplicate
    far = await service.create_report(
        category="open_burning",
        description="Separate burning pile further north.",
        lat=28.633,
        lon=77.220,
        user_lat=28.633,
        user_lon=77.220,
        reporter_hash="u3",
        now=now + timedelta(minutes=40),
    )
    assert far["duplicate_of"] is None


@pytest.mark.asyncio
async def test_confirm_and_flag_hide_on_three_flags() -> None:
    store = MemoryStore()
    service = ReportService(store)
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)

    created = await service.create_report(
        category="smoke",
        description="Strong smoke near metro station gate.",
        lat=28.630,
        lon=77.220,
        user_lat=28.630,
        user_lon=77.220,
        reporter_hash="creator",
        now=now,
    )
    rid = created["report"]["id"]

    # Confirm once per reporter hash
    c1 = await service.confirm_report(report_id=rid, reporter_hash="u1", now=now)
    assert c1["confirmations"] == 1
    assert c1["already_confirmed"] is False

    c1_repeat = await service.confirm_report(report_id=rid, reporter_hash="u1", now=now)
    assert c1_repeat["confirmations"] == 1
    assert c1_repeat["already_confirmed"] is True

    # Flag 3 times by distinct reporter hashes -> hidden
    f1 = await service.flag_report(report_id=rid, reporter_hash="f1", now=now)
    assert f1["status"] == "published"
    f2 = await service.flag_report(report_id=rid, reporter_hash="f2", now=now)
    assert f2["status"] == "published"
    f3 = await service.flag_report(report_id=rid, reporter_hash="f3", now=now)
    assert f3["status"] == "hidden"

    # Hidden report no longer appears in nearby
    nearby, _ = await service.list_nearby(lat=28.630, lon=77.220, now=now)
    assert nearby == []


@pytest.mark.asyncio
async def test_expiry_boundary_and_rate_limits() -> None:
    store = MemoryStore()
    service = ReportService(store)
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)

    # Create 3 reports in 1 hour -> allowed; 4th -> RateLimitedError
    for idx in range(3):
        await service.create_report(
            category="other",
            description=f"Distinct observation number {idx} at spot.",
            lat=28.630 + idx * 0.01,
            lon=77.220,
            user_lat=28.630,
            user_lon=77.220,
            reporter_hash="spammer",
            now=now,
        )

    with pytest.raises(RateLimitedError):
        await service.create_report(
            category="other",
            description="Fourth observation within the same hour.",
            lat=28.660,
            lon=77.220,
            user_lat=28.630,
            user_lon=77.220,
            reporter_hash="spammer",
            now=now,
        )

    # Expiry boundary: 'other' has 24h TTL
    before_exp, _ = await service.list_nearby(
        lat=28.630, lon=77.220, radius_km=10.0, hours=48, now=now + timedelta(hours=23, minutes=59)
    )
    assert len(before_exp) == 3

    at_exp, _ = await service.list_nearby(
        lat=28.630, lon=77.220, radius_km=10.0, hours=48, now=now + timedelta(hours=24)
    )
    assert len(at_exp) == 0


@pytest.mark.asyncio
async def test_demo_reports_read_only_and_confirm_not_found() -> None:
    store = MemoryStore()
    service = ReportService(store)

    nearby, warnings = await service.list_nearby(
        lat=28.6315, lon=77.2167, radius_km=5.0, hours=24, is_demo=True
    )
    assert len(nearby) >= 3
    assert warnings == []

    with pytest.raises(ValidationAppError, match="sample-data mode"):
        await service.create_report(
            category="smoke",
            description="Trying to post in demo mode here.",
            lat=28.631,
            lon=77.217,
            user_lat=28.631,
            user_lon=77.217,
            reporter_hash="u1",
            is_demo=True,
        )

    with pytest.raises(NotFoundError):
        await service.confirm_report(report_id="missing-id", reporter_hash="u1")
