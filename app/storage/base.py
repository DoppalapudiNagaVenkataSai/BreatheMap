"""Storage abstract protocols for BreatheMap."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ReportStore(Protocol):
    """Protocol for community reports persistence."""

    async def create_report(self, report_data: dict[str, Any]) -> str:
        """Create a new report and return its ID."""
        ...

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        """Retrieve report by ID."""
        ...

    async def list_nearby(
        self, geohash5_list: list[str], max_results: int = 50
    ) -> list[dict[str, Any]]:
        """List reports in matching geohash buckets."""
        ...

    async def update_report(self, report_id: str, updates: dict[str, Any]) -> bool:
        """Update report fields."""
        ...

    async def increment_report_field(
        self, report_id: str, field: str, amount: int = 1
    ) -> int | None:
        """Atomically increment an integer field on a report and return new value."""
        ...


@runtime_checkable
class VoteStore(Protocol):
    """Protocol for confirmations and flags."""

    async def add_vote(self, report_id: str, vote_type: str, reporter_hash: str) -> bool:
        """Record a confirmation or flag if not already submitted today."""
        ...

    async def has_voted(self, report_id: str, vote_type: str, reporter_hash: str) -> bool:
        """Check if reporter hash has already submitted vote for report."""
        ...


@runtime_checkable
class CacheStore(Protocol):
    """Protocol for L2 cache storage."""

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get cached item."""
        ...

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        """Set cache item with TTL."""
        ...


@runtime_checkable
class CounterStore(Protocol):
    """Protocol for daily and minute usage counters."""

    async def increment(self, key: str, window_seconds: int = 86400) -> int:
        """Increment counter and return current value."""
        ...

    async def get_count(self, key: str) -> int:
        """Get current counter value."""
        ...


@runtime_checkable
class StoreProtocol(ReportStore, VoteStore, CacheStore, CounterStore, Protocol):
    """Unified storage protocol combining Report, Vote, Cache, and Counter stores."""

    ...
