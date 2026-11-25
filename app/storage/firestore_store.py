"""Firestore asynchronous storage implementation using google-cloud-firestore."""

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2 import service_account

from app.core.errors import StorageUnavailableError


def _parse_iso_utc(value: Any) -> datetime | None:
    """Parse an ISO timestamp string or datetime into a UTC-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _is_expired(data: dict[str, Any], now: datetime) -> bool:
    """Return True if document has an expires_at timestamp in the past."""
    expires_at = _parse_iso_utc(data.get("expires_at"))
    if expires_at is None:
        return False
    return expires_at <= now


def _safe_doc_id(raw_key: str) -> str:
    """Convert an arbitrary key into a Firestore-safe document ID without slashes."""
    if "/" not in raw_key and len(raw_key) <= 128:
        return raw_key
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def build_firestore_client(
    credentials_b64: str | None, project_id: str | None = None
) -> firestore.AsyncClient:
    """Instantiate a Firestore AsyncClient from base64-encoded service account JSON."""
    if not credentials_b64:
        raise StorageUnavailableError("Firestore credentials are not configured.")
    try:
        raw_json = base64.b64decode(credentials_b64.strip()).decode("utf-8")
        info = json.loads(raw_json)
        creds = service_account.Credentials.from_service_account_info(info)  # type: ignore[no-untyped-call]
        resolved_project = project_id or info.get("project_id")
        return firestore.AsyncClient(project=resolved_project, credentials=creds)
    except Exception as exc:
        raise StorageUnavailableError("Failed to initialize Firestore client.") from exc


class FirestoreStore:
    """Firestore-backed store implementing Report, Vote, Cache, and Counter protocols."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_credentials_b64(
        cls, credentials_b64: str | None, project_id: str | None = None
    ) -> "FirestoreStore":
        """Create a FirestoreStore from base64-encoded service account credentials."""
        client = build_firestore_client(credentials_b64, project_id=project_id)
        return cls(client)

    async def close(self) -> None:
        """Close the underlying Firestore client if supported."""
        close_fn = getattr(self._client, "close", None)
        if callable(close_fn):
            res = close_fn()
            if hasattr(res, "__await__"):
                await res

    # --- ReportStore ---

    async def create_report(self, report_data: dict[str, Any]) -> str:
        """Create a new report document in the reports collection."""
        report_id = str(report_data.get("id") or uuid.uuid4())
        payload = dict(report_data)
        payload["id"] = report_id
        try:
            doc_ref = self._client.collection("reports").document(report_id)
            await doc_ref.set(payload)
            return report_id
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to save report.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to save report.") from exc

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        """Retrieve a report by ID, returning None if missing or expired."""
        try:
            snap = await self._client.collection("reports").document(report_id).get()
            if not snap.exists:
                return None
            data = snap.to_dict() or {}
            data.setdefault("id", snap.id)
            if _is_expired(data, datetime.now(UTC)):
                return None
            return dict(data)
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to read report.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to read report.") from exc

    async def list_nearby(
        self, geohash5_list: list[str], max_results: int = 50
    ) -> list[dict[str, Any]]:
        """Query reports in up to 9 geohash5 cells and filter status/expiry in Python."""
        if not geohash5_list:
            return []
        buckets = geohash5_list[:9]
        now = datetime.now(UTC)
        try:
            query = self._client.collection("reports").where(
                filter=FieldFilter("geohash5", "in", buckets)
            )
            results: list[dict[str, Any]] = []
            async for snap in query.stream():
                data = snap.to_dict() or {}
                data.setdefault("id", snap.id)
                if data.get("status") != "published":
                    continue
                if _is_expired(data, now):
                    continue
                results.append(dict(data))
                if len(results) >= max_results:
                    break
            return results
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to query nearby reports.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to query nearby reports.") from exc

    async def update_report(self, report_id: str, updates: dict[str, Any]) -> bool:
        """Update report fields in Firestore."""
        try:
            doc_ref = self._client.collection("reports").document(report_id)
            snap = await doc_ref.get()
            if not snap.exists:
                return False
            await doc_ref.update(dict(updates))
            return True
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to update report.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to update report.") from exc

    async def increment_report_field(
        self, report_id: str, field: str, amount: int = 1
    ) -> int | None:
        """Atomically increment an integer field on a report and return the new value."""
        try:
            doc_ref = self._client.collection("reports").document(report_id)
            snap = await doc_ref.get()
            if not snap.exists:
                return None
            await doc_ref.update({field: firestore.Increment(amount)})
            updated = await doc_ref.get()
            data = updated.to_dict() or {}
            return int(data.get(field, 0))
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to update report counter.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to update report counter.") from exc

    # --- VoteStore ---

    async def add_vote(self, report_id: str, vote_type: str, reporter_hash: str) -> bool:
        """Record a confirmation or flag if not already submitted."""
        vote_id = f"{report_id}:{vote_type}:{reporter_hash}"
        now = datetime.now(UTC)
        expires_at = (now + timedelta(days=7)).isoformat()
        try:
            doc_ref = self._client.collection("report_votes").document(vote_id)
            snap = await doc_ref.get()
            if snap.exists:
                existing = snap.to_dict() or {}
                if not _is_expired(existing, now):
                    return False
            await doc_ref.set(
                {
                    "report_id": report_id,
                    "kind": vote_type,
                    "created_at": now.isoformat(),
                    "expires_at": expires_at,
                }
            )
            return True
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to record vote.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to record vote.") from exc

    async def has_voted(self, report_id: str, vote_type: str, reporter_hash: str) -> bool:
        """Check if reporter hash has already submitted vote for report."""
        vote_id = f"{report_id}:{vote_type}:{reporter_hash}"
        try:
            snap = await self._client.collection("report_votes").document(vote_id).get()
            if not snap.exists:
                return False
            data = snap.to_dict() or {}
            return not _is_expired(data, datetime.now(UTC))
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to check vote.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to check vote.") from exc

    # --- CacheStore ---

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get cached JSON item by sha256 key, ignoring expired entries."""
        doc_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
        try:
            snap = await self._client.collection("cache").document(doc_id).get()
            if not snap.exists:
                return None
            data = snap.to_dict() or {}
            if _is_expired(data, datetime.now(UTC)):
                return None
            raw_value = data.get("value")
            if isinstance(raw_value, str):
                parsed: dict[str, Any] = json.loads(raw_value)
                return parsed
            if isinstance(raw_value, dict):
                return dict(raw_value)
            return None
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to read cache.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to read cache.") from exc

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        """Store cached JSON item with TTL."""
        doc_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
        try:
            await (
                self._client.collection("cache")
                .document(doc_id)
                .set(
                    {
                        "value": json.dumps(value),
                        "expires_at": expires_at,
                    }
                )
            )
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to write cache.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to write cache.") from exc

    # --- CounterStore ---

    async def increment(self, key: str, window_seconds: int = 86400) -> int:
        """Atomically increment counter and reset if previous window expired."""
        doc_id = _safe_doc_id(key)
        now = datetime.now(UTC)
        new_expiry = (now + timedelta(seconds=window_seconds)).isoformat()
        try:
            doc_ref = self._client.collection("counters").document(doc_id)
            snap = await doc_ref.get()
            if not snap.exists or _is_expired(snap.to_dict() or {}, now):
                await doc_ref.set({"count": 1, "expires_at": new_expiry})
                return 1
            await doc_ref.update({"count": firestore.Increment(1)})
            updated = await doc_ref.get()
            data = updated.to_dict() or {}
            return int(data.get("count", 1))
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to update counter.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to update counter.") from exc

    async def get_count(self, key: str) -> int:
        """Get current non-expired counter value."""
        doc_id = _safe_doc_id(key)
        try:
            snap = await self._client.collection("counters").document(doc_id).get()
            if not snap.exists:
                return 0
            data = snap.to_dict() or {}
            if _is_expired(data, datetime.now(UTC)):
                return 0
            return int(data.get("count", 0))
        except GoogleAPIError as exc:
            raise StorageUnavailableError("Unable to read counter.") from exc
        except Exception as exc:
            raise StorageUnavailableError("Unable to read counter.") from exc
