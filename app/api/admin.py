"""Admin moderation API endpoints."""

import hmac
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.security import verify_same_origin
from app.dependencies import get_app_settings, get_store
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _verify_admin_token(request: Request, settings: Settings) -> None:
    """Verify Bearer ADMIN_TOKEN with constant-time comparison; 404 if unset."""
    if not settings.ADMIN_TOKEN:
        raise NotFoundError("Not found")

    auth_header = request.headers.get("authorization", "")
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        raise AppError(code="UNAUTHORIZED", message="Missing admin bearer token.", status_code=401)

    provided = auth_header[len(prefix) :].strip()
    if not hmac.compare_digest(provided.encode("utf-8"), settings.ADMIN_TOKEN.encode("utf-8")):
        raise AppError(code="FORBIDDEN", message="Invalid admin token.", status_code=403)


@router.post("/reports/{report_id}/hide")
async def admin_hide_report(
    report_id: str,
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """Hide a community report via admin bearer token."""
    _verify_admin_token(request, settings)
    verify_same_origin(request, settings)

    service = ReportService(get_store(request))
    result = await service.admin_hide_report(report_id)
    now_iso = datetime.now(UTC).isoformat()
    return {
        "data": result,
        "meta": {
            "source": ["breathewatch-admin"],
            "observed_at": now_iso,
            "fetched_at": now_iso,
            "is_demo": False,
            "cached": False,
            "warnings": [],
        },
    }
