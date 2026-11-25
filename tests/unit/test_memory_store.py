"""Test memory store implementation."""

import pytest

from app.storage.memory_store import MemoryStore


@pytest.mark.asyncio
async def test_memory_store_report_crud() -> None:
    store = MemoryStore()
    rep_id = await store.create_report(
        {
            "category": "smoke",
            "description": "Visible trash fire nearby",
            "geohash5": "ttnfv",
            "status": "published",
        }
    )
    assert rep_id is not None

    rep = await store.get_report(rep_id)
    assert rep is not None
    assert rep["category"] == "smoke"

    updated = await store.update_report(rep_id, {"status": "hidden"})
    assert updated is True
    rep_updated = await store.get_report(rep_id)
    assert rep_updated is not None
    assert rep_updated["status"] == "hidden"


@pytest.mark.asyncio
async def test_memory_store_cache_and_counters() -> None:
    store = MemoryStore()

    # Cache
    await store.set("cache_key", {"val": 42}, ttl_seconds=60)
    cached = await store.get("cache_key")
    assert cached == {"val": 42}

    # Expired cache
    await store.set("expired_key", {"val": 1}, ttl_seconds=-1)
    assert await store.get("expired_key") is None

    # Counters
    count = await store.increment("day_counter")
    assert count == 1
    count2 = await store.increment("day_counter")
    assert count2 == 2
    assert await store.get_count("day_counter") == 2


@pytest.mark.asyncio
async def test_memory_store_votes() -> None:
    store = MemoryStore()
    assert await store.has_voted("rep1", "confirm", "hashA") is False
    added = await store.add_vote("rep1", "confirm", "hashA")
    assert added is True
    assert await store.has_voted("rep1", "confirm", "hashA") is True

    # Duplicate vote
    duplicate = await store.add_vote("rep1", "confirm", "hashA")
    assert duplicate is False
