"""Gemini quota manager using CounterStore with E36 fallback."""

import asyncio
from datetime import UTC, datetime

from app.config import Settings
from app.core.errors import RateLimitedError, StorageUnavailableError
from app.core.rate_limit import limiter
from app.storage.base import CounterStore

FALLBACK_CONSERVATIVE_RPM = 2


class QuotaManager:
    """Checks global daily, global RPM, and per-user daily Gemini budgets."""

    def __init__(self, store: CounterStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    @staticmethod
    def _keys(reporter_hash: str, now: datetime) -> tuple[str, str, str]:
        utc_day = now.strftime("%Y-%m-%d")
        utc_min = now.strftime("%Y-%m-%dT%H:%M")
        return (
            f"ai_daily:{utc_day}",
            f"ai_rpm:{utc_min}",
            f"ai_user:{reporter_hash}:{utc_day}",
        )

    async def can_use_ai(
        self, reporter_hash: str, now: datetime | None = None
    ) -> tuple[bool, str | None]:
        """Check whether Gemini can be called without incrementing any counter."""
        if not self.settings.GEMINI_ENABLED or not self.settings.GEMINI_API_KEY:
            return False, "gemini_disabled"

        ref_now = now or datetime.now(UTC)
        daily_key, rpm_key, user_key = self._keys(reporter_hash, ref_now)

        try:
            daily_count, rpm_count, user_count = await asyncio.gather(
                self.store.get_count(daily_key),
                self.store.get_count(rpm_key),
                self.store.get_count(user_key),
            )
            if daily_count >= self.settings.GEMINI_DAILY_LIMIT:
                return False, "quota_daily_exhausted"

            if rpm_count >= self.settings.GEMINI_RPM_LIMIT:
                return False, "quota_rpm_exhausted"

            if user_count >= self.settings.ASSISTANT_AI_PER_IP_PER_DAY:
                return False, "quota_user_exhausted"

            return True, None
        except StorageUnavailableError:
            # E36: fall back to per-instance limit with conservative 2 AI calls/min
            try:
                limiter.check_and_record("ai_fallback_rpm", FALLBACK_CONSERVATIVE_RPM, 60)
                return True, None
            except RateLimitedError:
                return False, "quota_fallback_rpm_exhausted"

    async def record_ai_call(self, reporter_hash: str, now: datetime | None = None) -> None:
        """Increment quota counters ONLY when a Gemini call is actually made."""
        ref_now = now or datetime.now(UTC)
        daily_key, rpm_key, user_key = self._keys(reporter_hash, ref_now)
        try:
            await asyncio.gather(
                self.store.increment(daily_key, window_seconds=86400),
                self.store.increment(rpm_key, window_seconds=60),
                self.store.increment(user_key, window_seconds=86400),
            )
        except StorageUnavailableError:
            return
