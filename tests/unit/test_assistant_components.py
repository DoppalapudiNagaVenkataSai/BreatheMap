"""Unit tests for assistant facts, validator, fallback templates, and quota manager."""

from datetime import UTC, datetime

import pytest

from app.assistant.facts import (
    FactsBundle,
    build_facts_json,
    build_user_reports_block,
    estimate_tokens,
    extract_allowed_numbers,
)
from app.assistant.fallback import build_quick_reply
from app.assistant.gemini_client import AssistantDraft
from app.assistant.intents import Intent
from app.assistant.quota import QuotaManager
from app.assistant.validator import validate_draft
from app.config import Settings
from app.core.errors import StorageUnavailableError
from app.storage.memory_store import MemoryStore


def test_facts_budget_and_reports_truncation() -> None:
    bundle = FactsBundle()
    for i in range(120):
        bundle.add_fact(f"metric_{i}", f"some-long-value-{i}-" + "x" * 30, unit="µg/m³")

    facts_json = build_facts_json(bundle)
    assert estimate_tokens(facts_json) <= 1500

    reports = [{"category": "smoke", "description": f"Report {i}: " + "a" * 200} for i in range(8)]
    block = build_user_reports_block(reports)
    lines = block.splitlines()
    assert len(lines) == 5
    assert all(len(line) <= 140 for line in lines)


def test_validator_rules() -> None:
    bundle = FactsBundle()
    bundle.add_fact("pm25", 142.4, unit="µg/m³")
    bundle.add_fact("duration_min", 30, unit="min")
    facts_json = build_facts_json(bundle)
    allowed = extract_allowed_numbers(facts_json)
    valid_ids = bundle.valid_ids()

    good = AssistantDraft(
        summary="PM2.5 is around 142 µg/m³ for your 30 min outing.",
        recommendation="Consider a shorter session with lower estimated exposure.",
        reasons=["PM2.5 is 142.4 µg/m³."],
        caveats=["Modelled data."],
        used_fact_ids=["F1", "F2"],
    )
    ok, err = validate_draft(good, allowed_numbers=allowed, valid_fact_ids=valid_ids)
    assert ok is True
    assert err is None

    # Invented number fails
    bad_num = good.model_copy(update={"summary": "PM2.5 is 999 µg/m³ today."})
    ok, err = validate_draft(bad_num, allowed_numbers=allowed, valid_fact_ids=valid_ids)
    assert ok is False and err == "validator_ungrounded_number"

    # Banned word fails
    bad_word = good.model_copy(update={"recommendation": "This route is completely safe."})
    ok, err = validate_draft(bad_word, allowed_numbers=allowed, valid_fact_ids=valid_ids)
    assert ok is False and err == "validator_banned_phrase"

    # Bad fact ID fails
    bad_id = good.model_copy(update={"used_fact_ids": ["F99"]})
    ok, err = validate_draft(bad_id, allowed_numbers=allowed, valid_fact_ids=valid_ids)
    assert ok is False and err == "validator_invalid_fact_id"

    # URL fails
    bad_url = good.model_copy(update={"caveats": ["See https://example.com"]})
    ok, err = validate_draft(bad_url, allowed_numbers=allowed, valid_fact_ids=valid_ids)
    assert ok is False and err == "validator_url"


def test_fallback_quick_replies_for_all_intents() -> None:
    sample_cards = [
        {
            "type": "air_summary",
            "data": {"band": "Poor", "index": 240, "pm25": 102, "source": "Demo"},
        },
        {
            "type": "time_window",
            "data": {
                "cleanest": {
                    "start_time": "2026-11-25T13:00:00",
                    "end_time": "2026-11-25T16:00:00",
                    "avg_pm25": 68.0,
                },
                "worst": {
                    "start_time": "2026-11-25T21:00:00",
                    "end_time": "2026-11-25T00:00:00",
                    "avg_pm25": 150.0,
                },
            },
        },
        {
            "type": "activity_advice",
            "data": {"summary": "Advice for Jog at L4", "advice": "Shorten session."},
        },
        {
            "type": "route_comparison",
            "data": {
                "options": [
                    {
                        "mode": "metro",
                        "status": "available",
                        "dose_ug": 40.0,
                        "duration_min": 30,
                        "is_estimated": True,
                    },
                    {
                        "mode": "car",
                        "status": "available",
                        "dose_ug": 90.0,
                        "duration_min": 20,
                        "is_estimated": False,
                    },
                ],
                "departure_suggestion": {"time": "2026-11-25T14:30:00", "reduction_pct": 35},
            },
        },
        {"type": "home_tips", "data": [{"title": "Keep windows closed"}]},
        {"type": "reports", "data": [{"id": "1", "category": "smoke"}]},
        {"type": "glossary", "data": {"term": "pm25", "definition": "Fine particles."}},
    ]
    for intent in (
        Intent.AIR_NOW,
        Intent.BEST_TIME,
        Intent.ACTIVITY_ADVICE,
        Intent.ROUTE_COMPARE,
        Intent.HOME_TIPS,
        Intent.REPORTS_NEARBY,
        Intent.REPORT_HELP,
        Intent.EXPLAIN,
    ):
        reply = build_quick_reply(intent, cards=sample_cards)
        assert reply["summary"]
        assert reply["recommendation"]


@pytest.mark.asyncio
async def test_quota_manager_limits_and_e36_fallback() -> None:
    store = MemoryStore()
    settings = Settings(
        GEMINI_ENABLED=True,
        GEMINI_API_KEY="fake-key",
        GEMINI_DAILY_LIMIT=2,
        GEMINI_RPM_LIMIT=4,
        ASSISTANT_AI_PER_IP_PER_DAY=5,
    )
    qm = QuotaManager(store, settings)
    now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

    # Check before increment does NOT consume quota
    ok, _ = await qm.can_use_ai("u1", now=now)
    assert ok is True
    assert await store.get_count("ai_daily:2026-11-25") == 0

    await qm.record_ai_call("u1", now=now)
    await qm.record_ai_call("u1", now=now)

    ok2, reason2 = await qm.can_use_ai("u1", now=now)
    assert ok2 is False
    assert reason2 == "quota_daily_exhausted"

    # StorageUnavailableError fallback (E36)
    class FailingCounterStore:
        async def increment(self, key: str, window_seconds: int = 86400) -> int:
            raise StorageUnavailableError()

        async def get_count(self, key: str) -> int:
            raise StorageUnavailableError()

    qm_fail = QuotaManager(FailingCounterStore(), settings)
    ok_fb, _ = await qm_fail.can_use_ai("u1", now=now)
    assert ok_fb is True
