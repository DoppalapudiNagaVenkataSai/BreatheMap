"""BreatheWatch community reports service implementing Section 8.13 rules."""

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.constants import (
    REPORT_CATEGORIES,
    REPORT_CREATE_PER_DAY,
    REPORT_CREATE_PER_HOUR,
    REPORT_DEFAULT_HOURS,
    REPORT_DEFAULT_RADIUS_KM,
    REPORT_DESC_MAX_LEN,
    REPORT_DESC_MIN_LEN,
    REPORT_DUPLICATE_RADIUS_M,
    REPORT_DUPLICATE_WINDOW_HOURS,
    REPORT_FLAG_HIDE_THRESHOLD,
    REPORT_MAX_RADIUS_KM,
    REPORT_MAX_RESULTS,
    REPORT_MAX_USER_DISTANCE_KM,
    REPORT_ROUTE_RADIUS_M,
    REPORT_STATUS_LABEL,
    REPORT_TTL_HOURS,
    REPORT_VOTE_PER_DAY,
)
from app.core.errors import (
    NotFoundError,
    OutOfRangeError,
    RateLimitedError,
    StorageUnavailableError,
    ValidationAppError,
)
from app.domain.geo import (
    geohash_encode,
    geohash_neighbors,
    haversine_m,
    line_midpoint,
    point_to_segment_distance_m,
)
from app.storage.base import StoreProtocol

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
BLOCKED_WORDS_PATH = DATA_DIR / "knowledge" / "blocked_words.txt"
DEMO_REPORTS_PATH = DATA_DIR / "demo" / "delhi_reports.json"

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_URL_RE = re.compile(
    r"(https?://\S+|www\.\S+|\b[a-z0-9-]+\.(com|org|net|in|io|co|edu|gov|info|biz)\b)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")


@lru_cache(maxsize=1)
def load_blocked_words() -> tuple[str, ...]:
    """Load blocked words list from data/knowledge/blocked_words.txt."""
    if not BLOCKED_WORDS_PATH.exists():
        return ()
    words: list[str] = []
    for raw_line in BLOCKED_WORDS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lower()
        if line and not line.startswith("#"):
            words.append(line)
    return tuple(words)


def load_demo_reports(now: datetime | None = None) -> list[dict[str, Any]]:
    """Load synthetic Delhi demo reports with timestamps relative to now."""
    if not DEMO_REPORTS_PATH.exists():
        return []
    ref_now = now or datetime.now(UTC)
    raw_items: list[dict[str, Any]] = json.loads(DEMO_REPORTS_PATH.read_text(encoding="utf-8"))
    reports: list[dict[str, Any]] = []
    for item in raw_items:
        category = str(item.get("category", "other"))
        age_min = int(item.get("age_minutes", 60))
        created = ref_now - timedelta(minutes=age_min)
        ttl_h = REPORT_TTL_HOURS.get(category, 24)
        expires = created + timedelta(hours=ttl_h)
        lat = round(float(item["lat"]), 3)
        lon = round(float(item["lon"]), 3)
        reports.append(
            {
                "id": str(item["id"]),
                "category": category,
                "description": str(item["description"]),
                "lat": lat,
                "lon": lon,
                "geohash5": geohash_encode(lat, lon, precision=5),
                "geohash6": geohash_encode(lat, lon, precision=6),
                "created_at": created.isoformat(),
                "expires_at": expires.isoformat(),
                "status": "published",
                "confirmations": int(item.get("confirmations", 0)),
                "flags": 0,
                "is_demo": True,
            }
        )
    return reports


def _parse_dt(value: Any) -> datetime | None:
    """Parse ISO string or datetime to UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def sanitize_and_validate_description(raw_desc: str) -> str:
    """Strip control characters and enforce length, privacy, and blocked-word rules."""
    cleaned = _CONTROL_CHAR_RE.sub(" ", raw_desc).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) < REPORT_DESC_MIN_LEN or len(cleaned) > REPORT_DESC_MAX_LEN:
        raise ValidationAppError(
            f"Description must be {REPORT_DESC_MIN_LEN}-{REPORT_DESC_MAX_LEN} characters."
        )
    if _EMAIL_RE.search(cleaned):
        raise ValidationAppError("Descriptions cannot contain email addresses.")
    if _URL_RE.search(cleaned):
        raise ValidationAppError("Descriptions cannot contain web links or URLs.")
    if _PHONE_RE.search(cleaned):
        raise ValidationAppError(
            "Descriptions cannot contain phone numbers or personal contact details."
        )
    lowered = cleaned.lower()
    for word in load_blocked_words():
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            raise ValidationAppError(
                "Description contains a blocked term. Please describe only the pollution observed."
            )
    return cleaned


def _format_public_report(rep: dict[str, Any], distance_km: float | None = None) -> dict[str, Any]:
    """Shape a stored report into its public API representation (never exposing reporter_hash)."""
    payload: dict[str, Any] = {
        "id": rep["id"],
        "category": rep["category"],
        "description": rep["description"],
        "lat": rep["lat"],
        "lon": rep["lon"],
        "created_at": rep["created_at"],
        "expires_at": rep["expires_at"],
        "confirmations": int(rep.get("confirmations", 0)),
        "status_label": REPORT_STATUS_LABEL,
        "is_demo": bool(rep.get("is_demo", False)),
    }
    if distance_km is not None:
        payload["distance_km"] = round(distance_km, 2)
    return payload


class ReportService:
    """Service enforcing all BreatheWatch validation, duplicate, rate-limit, and query rules."""

    def __init__(self, store: StoreProtocol) -> None:
        self.store = store

    async def _find_duplicate_report(
        self,
        *,
        category: str,
        lat: float,
        lon: float,
        buckets: list[str],
        ref_now: datetime,
    ) -> dict[str, Any] | None:
        """Return an existing duplicate report within 300 m and 2 hours, if any."""
        candidates = await self.store.list_nearby(buckets, max_results=REPORT_MAX_RESULTS)
        dup_cutoff = ref_now - timedelta(hours=REPORT_DUPLICATE_WINDOW_HOURS)
        for cand in candidates:
            if cand.get("status") != "published" or cand.get("category") != category:
                continue
            cand_expires = _parse_dt(cand.get("expires_at"))
            cand_created = _parse_dt(cand.get("created_at"))
            if not cand_expires or cand_expires <= ref_now:
                continue
            if not cand_created or cand_created < dup_cutoff:
                continue
            cand_dist_m = haversine_m(lat, lon, float(cand["lat"]), float(cand["lon"]))
            if cand_dist_m <= REPORT_DUPLICATE_RADIUS_M:
                return {
                    "report": _format_public_report(cand, distance_km=cand_dist_m / 1000.0),
                    "duplicate_of": cand["id"],
                    "message": "Someone already reported this — tap 'I see this too'.",
                }
        return None

    async def _enforce_create_rate_limits(self, reporter_hash: str) -> None:
        """Enforce hourly and daily report creation limits per reporter hash."""
        hr_count = await self.store.increment(
            f"report_create_hr:{reporter_hash}", window_seconds=3600
        )
        if hr_count > REPORT_CREATE_PER_HOUR:
            raise RateLimitedError(
                f"You can post up to {REPORT_CREATE_PER_HOUR} reports per hour. "
                "Please try again later."
            )
        day_count = await self.store.increment(
            f"report_create_day:{reporter_hash}", window_seconds=86400
        )
        if day_count > REPORT_CREATE_PER_DAY:
            raise RateLimitedError(
                f"You have reached the daily limit of {REPORT_CREATE_PER_DAY} reports."
            )

    async def create_report(
        self,
        *,
        category: str,
        description: str,
        lat: float,
        lon: float,
        user_lat: float,
        user_lon: float,
        reporter_hash: str,
        is_demo: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Validate, deduplicate, rate-limit, and persist a community report."""
        if is_demo:
            raise ValidationAppError("Posting is disabled in sample-data mode.")

        if category not in REPORT_CATEGORIES:
            raise ValidationAppError("Invalid report category.")

        cleaned_desc = sanitize_and_validate_description(description)

        rounded_lat = round(float(lat), 3)
        rounded_lon = round(float(lon), 3)
        dist_from_user_km = (
            haversine_m(rounded_lat, rounded_lon, float(user_lat), float(user_lon)) / 1000.0
        )
        if dist_from_user_km > REPORT_MAX_USER_DISTANCE_KM:
            raise OutOfRangeError("Reports must be near your current location.")

        ref_now = now or datetime.now(UTC)
        gh5 = geohash_encode(rounded_lat, rounded_lon, precision=5)
        gh6 = geohash_encode(rounded_lat, rounded_lon, precision=6)
        buckets = [gh5, *geohash_neighbors(gh5)]

        dup = await self._find_duplicate_report(
            category=category,
            lat=rounded_lat,
            lon=rounded_lon,
            buckets=buckets,
            ref_now=ref_now,
        )
        if dup is not None:
            return dup

        await self._enforce_create_rate_limits(reporter_hash)

        ttl_hours = REPORT_TTL_HOURS.get(category, 24)
        expires_at = ref_now + timedelta(hours=ttl_hours)
        report_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "id": report_id,
            "category": category,
            "description": cleaned_desc,
            "lat": rounded_lat,
            "lon": rounded_lon,
            "geohash5": gh5,
            "geohash6": gh6,
            "created_at": ref_now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "published",
            "confirmations": 0,
            "flags": 0,
            "reporter_hash": reporter_hash,
            "is_demo": False,
        }
        await self.store.create_report(record)
        return {
            "report": _format_public_report(record, distance_km=0.0),
            "duplicate_of": None,
            "message": f"Thanks — your report is visible for {ttl_hours} hours.",
        }

    async def list_nearby(
        self,
        *,
        lat: float,
        lon: float,
        radius_km: float = REPORT_DEFAULT_RADIUS_KM,
        hours: int = REPORT_DEFAULT_HOURS,
        category: str | None = None,
        is_demo: bool = False,
        now: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """List published, non-expired reports near a point, sorted by distance then recency."""
        if category is not None and category != "" and category not in REPORT_CATEGORIES:
            raise ValidationAppError("Invalid report category filter.")

        effective_radius = min(max(float(radius_km), 0.1), REPORT_MAX_RADIUS_KM)
        ref_now = now or datetime.now(UTC)
        cutoff = ref_now - timedelta(hours=hours)
        warnings: list[str] = []

        if is_demo:
            raw_reports = load_demo_reports(now=ref_now)
        else:
            gh5 = geohash_encode(lat, lon, precision=5)
            buckets = [gh5, *geohash_neighbors(gh5)]
            try:
                raw_reports = await self.store.list_nearby(buckets, max_results=REPORT_MAX_RESULTS)
            except StorageUnavailableError:
                warnings.append("Community reports are temporarily unavailable.")
                return [], warnings

        matched: list[tuple[float, float, dict[str, Any]]] = []
        for rep in raw_reports:
            if rep.get("status") != "published":
                continue
            expires_at = _parse_dt(rep.get("expires_at"))
            created_at = _parse_dt(rep.get("created_at"))
            if not expires_at or expires_at <= ref_now:
                continue
            if not created_at or created_at < cutoff:
                continue
            if category and rep.get("category") != category:
                continue
            dist_km = haversine_m(lat, lon, float(rep["lat"]), float(rep["lon"])) / 1000.0
            if dist_km > effective_radius:
                continue
            formatted = _format_public_report(rep, distance_km=dist_km)
            matched.append((dist_km, -created_at.timestamp(), formatted))

        matched.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in matched[:REPORT_MAX_RESULTS]], warnings

    async def list_along_route(
        self,
        *,
        coords: list[tuple[float, float]],
        is_demo: bool = False,
        now: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Find published, non-expired reports within 200 m of a route polyline."""
        if not coords:
            return [], []
        ref_now = now or datetime.now(UTC)
        warnings: list[str] = []

        if is_demo:
            candidates = load_demo_reports(now=ref_now)
        else:
            mid = line_midpoint(coords)
            gh5 = geohash_encode(mid[0], mid[1], precision=5)
            buckets = [gh5, *geohash_neighbors(gh5)]
            try:
                candidates = await self.store.list_nearby(buckets, max_results=REPORT_MAX_RESULTS)
            except StorageUnavailableError:
                warnings.append("Community reports along route are temporarily unavailable.")
                return [], warnings

        matched: list[dict[str, Any]] = []
        for rep in candidates:
            if rep.get("status") != "published":
                continue
            expires_at = _parse_dt(rep.get("expires_at"))
            if not expires_at or expires_at <= ref_now:
                continue
            rlat, rlon = rep.get("lat"), rep.get("lon")
            if rlat is None or rlon is None:
                continue
            for i in range(len(coords) - 1):
                dist_m = point_to_segment_distance_m(
                    float(rlat),
                    float(rlon),
                    coords[i][0],
                    coords[i][1],
                    coords[i + 1][0],
                    coords[i + 1][1],
                )
                if dist_m <= REPORT_ROUTE_RADIUS_M:
                    matched.append(_format_public_report(rep))
                    break
        return matched, warnings

    async def confirm_report(
        self,
        *,
        report_id: str,
        reporter_hash: str,
        is_demo: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Increment confirmations for a report (one per reporter hash)."""
        if is_demo:
            raise ValidationAppError("Posting is disabled in sample-data mode.")

        ref_now = now or datetime.now(UTC)
        report = await self.store.get_report(report_id)
        if not report or report.get("status") != "published":
            raise NotFoundError("Report not found or expired.")
        expires_at = _parse_dt(report.get("expires_at"))
        if not expires_at or expires_at <= ref_now:
            raise NotFoundError("Report not found or expired.")

        vote_count = await self.store.increment(
            f"report_vote_day:{reporter_hash}", window_seconds=86400
        )
        if vote_count > REPORT_VOTE_PER_DAY:
            raise RateLimitedError("Daily confirm/flag limit reached. Please try again tomorrow.")

        added = await self.store.add_vote(report_id, "confirm", reporter_hash)
        if added:
            updated_count = await self.store.increment_report_field(report_id, "confirmations", 1)
            confirmations = (
                updated_count
                if updated_count is not None
                else int(report.get("confirmations", 0)) + 1
            )
        else:
            confirmations = int(report.get("confirmations", 0))

        return {"confirmations": confirmations, "already_confirmed": not added}

    async def flag_report(
        self,
        *,
        report_id: str,
        reporter_hash: str,
        is_demo: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Flag a report (one per reporter hash); hide when flags reach threshold (3)."""
        if is_demo:
            raise ValidationAppError("Posting is disabled in sample-data mode.")

        ref_now = now or datetime.now(UTC)
        report = await self.store.get_report(report_id)
        if not report or report.get("status") == "hidden":
            raise NotFoundError("Report not found or expired.")
        expires_at = _parse_dt(report.get("expires_at"))
        if not expires_at or expires_at <= ref_now:
            raise NotFoundError("Report not found or expired.")

        vote_count = await self.store.increment(
            f"report_vote_day:{reporter_hash}", window_seconds=86400
        )
        if vote_count > REPORT_VOTE_PER_DAY:
            raise RateLimitedError("Daily confirm/flag limit reached. Please try again tomorrow.")

        status = str(report.get("status", "published"))
        added = await self.store.add_vote(report_id, "flag", reporter_hash)
        if added:
            new_flags = await self.store.increment_report_field(report_id, "flags", 1)
            flags_val = new_flags if new_flags is not None else int(report.get("flags", 0)) + 1
            if flags_val >= REPORT_FLAG_HIDE_THRESHOLD:
                await self.store.update_report(report_id, {"status": "hidden"})
                status = "hidden"

        return {"status": status}

    async def admin_hide_report(self, report_id: str) -> dict[str, Any]:
        """Hide a report via admin moderation."""
        report = await self.store.get_report(report_id)
        if not report:
            raise NotFoundError("Report not found.")
        await self.store.update_report(report_id, {"status": "hidden"})
        return {"status": "hidden"}
