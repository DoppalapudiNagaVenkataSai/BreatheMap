"""Test sliding window rate limiting."""

import pytest

from app.core.errors import RateLimitedError
from app.core.rate_limit import InMemorySlidingWindowLimiter


def test_rate_limiter_allows_under_limit() -> None:
    limiter = InMemorySlidingWindowLimiter()
    for _ in range(5):
        limiter.check_and_record("test_key", max_requests=5, window_seconds=60)


def test_rate_limiter_blocks_over_limit() -> None:
    limiter = InMemorySlidingWindowLimiter()
    for _ in range(3):
        limiter.check_and_record("test_key", max_requests=3, window_seconds=60)

    with pytest.raises(RateLimitedError):
        limiter.check_and_record("test_key", max_requests=3, window_seconds=60)
