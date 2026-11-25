"""In-memory asynchronous storage implementation."""

import time
from typing import Any


class MemoryStore:
    """In-memory store providing Report, Vote, Cache and Counter capabilities."""

    def __init__(self) -> None:
        self.reports: dict[str, dict[str, Any]] = {}
        self.votes: set[str] = set()
        self.cache: dict[str, tuple[dict[str, Any], float]] = {}
        self.counters: dict[str, list[float]] = {}

    # ReportStore
    async def create_report(self, report_data: dict[str, Any]) -> str:
        report_id = str(report_data.get("id") or len(self.reports) + 1)
        report_data["id"] = report_id
        self.reports[report_id] = dict(report_data)
        return report_id

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        return self.reports.get(report_id)

    async def list_nearby(
        self, geohash5_list: list[str], max_results: int = 50
    ) -> list[dict[str, Any]]:
        results = [
            r
            for r in self.reports.values()
            if r.get("geohash5") in geohash5_list and r.get("status") == "published"
        ]
        return results[:max_results]

    async def update_report(self, report_id: str, updates: dict[str, Any]) -> bool:
        if report_id in self.reports:
            self.reports[report_id].update(updates)
            return True
        return False

    # VoteStore
    async def add_vote(self, report_id: str, vote_type: str, reporter_hash: str) -> bool:
        vote_key = f"{report_id}:{vote_type}:{reporter_hash}"
        if vote_key in self.votes:
            return False
        self.votes.add(vote_key)
        return True

    async def has_voted(self, report_id: str, vote_type: str, reporter_hash: str) -> bool:
        vote_key = f"{report_id}:{vote_type}:{reporter_hash}"
        return vote_key in self.votes

    # CacheStore
    async def get(self, key: str) -> dict[str, Any] | None:
        if key not in self.cache:
            return None
        value, expires_at = self.cache[key]
        if time.monotonic() > expires_at:
            del self.cache[key]
            return None
        return value

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        self.cache[key] = (value, time.monotonic() + ttl_seconds)

    # CounterStore
    async def increment(self, key: str, window_seconds: int = 86400) -> int:
        now = time.monotonic()
        cutoff = now - window_seconds
        current_list = [ts for ts in self.counters.get(key, []) if ts > cutoff]
        current_list.append(now)
        self.counters[key] = current_list
        return len(current_list)

    async def get_count(self, key: str) -> int:
        return len(self.counters.get(key, []))

    def clear(self) -> None:
        """Reset all in-memory collections."""
        self.reports.clear()
        self.votes.clear()
        self.cache.clear()
        self.counters.clear()
