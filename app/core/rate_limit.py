"""Sliding window rate limiters (in-memory per-instance and store-ready)."""

import time
from collections import defaultdict

from app.core.errors import RateLimitedError


class InMemorySlidingWindowLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self) -> None:
        self._history: dict[str, list[float]] = defaultdict(list)

    def check_and_record(self, key: str, max_requests: int, window_seconds: int) -> None:
        """Check if request within window exceeds max_requests; raises RateLimitedError if so."""
        now = time.monotonic()
        cutoff = now - window_seconds

        timestamps = [ts for ts in self._history[key] if ts > cutoff]
        if len(timestamps) >= max_requests:
            raise RateLimitedError()

        timestamps.append(now)
        self._history[key] = timestamps

    def reset(self) -> None:
        """Reset history."""
        self._history.clear()


limiter = InMemorySlidingWindowLimiter()
