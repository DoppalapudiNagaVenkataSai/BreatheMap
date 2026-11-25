"""Unit tests for FirestoreStore using an offline fake async Firestore client."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from google.api_core.exceptions import GoogleAPIError

from app.core.errors import StorageUnavailableError
from app.storage.firestore_store import FirestoreStore


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict[str, Any] | None) -> None:
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, store: dict[str, dict[str, Any]], doc_id: str) -> None:
        self._store = store
        self.id = doc_id

    async def set(self, data: dict[str, Any]) -> None:
        self._store[self.id] = dict(data)

    async def get(self) -> FakeSnapshot:
        return FakeSnapshot(self.id, self._store.get(self.id))

    async def update(self, updates: dict[str, Any]) -> None:
        current = self._store[self.id]
        for k, v in updates.items():
            # Support firestore.Increment(n) sentinel object
            if hasattr(v, "value"):
                current[k] = int(current.get(k, 0)) + int(v.value)
            else:
                current[k] = v


class FakeQuery:
    def __init__(self, docs: dict[str, dict[str, Any]], field: str, values: list[Any]) -> None:
        self._docs = docs
        self._field = field
        self._values = set(values)

    async def stream(self) -> AsyncGenerator[FakeSnapshot, None]:
        for doc_id, data in self._docs.items():
            if data.get(self._field) in self._values:
                yield FakeSnapshot(doc_id, data)


class FakeCollection:
    def __init__(self, docs: dict[str, dict[str, Any]]) -> None:
        self._docs = docs

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self._docs, doc_id)

    def where(self, *, filter: Any) -> FakeQuery:
        return FakeQuery(self._docs, filter.field_path, filter.value)


class FakeAsyncFirestoreClient:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = {}
        return FakeCollection(self.collections[name])

    def close(self) -> None:
        return None


class FailingAsyncClient:
    def collection(self, name: str) -> Any:
        raise GoogleAPIError("Simulated outage")


@pytest.mark.asyncio
async def test_firestore_store_reports_votes_cache_counters() -> None:
    fake_client = FakeAsyncFirestoreClient()
    store = FirestoreStore(fake_client)
    now = datetime.now(UTC)

    # Create & Get Report
    rid = await store.create_report(
        {
            "id": "r1",
            "category": "smoke",
            "description": "Smoke near market",
            "geohash5": "ttnfv",
            "status": "published",
            "confirmations": 0,
            "expires_at": (now + timedelta(hours=12)).isoformat(),
        }
    )
    assert rid == "r1"
    fetched = await store.get_report("r1")
    assert fetched is not None
    assert fetched["category"] == "smoke"

    # Expired report is filtered out
    await store.create_report(
        {
            "id": "r-expired",
            "category": "smoke",
            "geohash5": "ttnfv",
            "status": "published",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
        }
    )
    assert await store.get_report("r-expired") is None

    # List nearby filters expired & non-published
    nearby = await store.list_nearby(["ttnfv", "ttnf5"])
    assert [r["id"] for r in nearby] == ["r1"]

    # Atomic increment & update
    new_conf = await store.increment_report_field("r1", "confirmations", 1)
    assert new_conf == 1
    assert await store.update_report("r1", {"status": "hidden"}) is True
    assert await store.update_report("missing", {"status": "hidden"}) is False

    # Votes
    assert await store.add_vote("r1", "confirm", "hash1") is True
    assert await store.has_voted("r1", "confirm", "hash1") is True
    assert await store.add_vote("r1", "confirm", "hash1") is False

    # Cache
    await store.set("k1", {"hello": "world"}, ttl_seconds=60)
    assert await store.get("k1") == {"hello": "world"}
    await store.set("k-exp", {"old": True}, ttl_seconds=-10)
    assert await store.get("k-exp") is None

    # Counters
    assert await store.get_count("c/1") == 0
    assert await store.increment("c/1", window_seconds=60) == 1
    assert await store.increment("c/1", window_seconds=60) == 2
    assert await store.get_count("c/1") == 2

    await store.close()


@pytest.mark.asyncio
async def test_firestore_store_maps_errors_to_storage_unavailable() -> None:
    store = FirestoreStore(FailingAsyncClient())

    with pytest.raises(StorageUnavailableError):
        await store.create_report({"id": "r1"})
    with pytest.raises(StorageUnavailableError):
        await store.get_report("r1")
    with pytest.raises(StorageUnavailableError):
        await store.list_nearby(["ttnfv"])
    with pytest.raises(StorageUnavailableError):
        await store.increment("c1")
    with pytest.raises(StorageUnavailableError):
        await store.get("k1")
