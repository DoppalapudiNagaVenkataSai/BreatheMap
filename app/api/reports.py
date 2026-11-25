"""BreatheWatch community reports API endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.constants import (
    API_RATE_LIMIT_PER_MINUTE,
    REPORT_DEFAULT_HOURS,
    REPORT_DEFAULT_RADIUS_KM,
    REPORT_MAX_RADIUS_KM,
)
from app.core.rate_limit import limiter
from app.core.security import get_client_ip, hash_subject, verify_same_origin
from app.dependencies import get_app_settings, get_store
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1", tags=["reports"])


class CreateReportRequest(BaseModel):
    """Request schema for creating a BreatheWatch community report."""

    model_config = ConfigDict(extra="forbid")

    category: str
    description: str = Field(..., min_length=1, max_length=500)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    user_lat: float = Field(..., ge=-90.0, le=90.0)
    user_lon: float = Field(..., ge=-180.0, le=180.0)


def _is_demo_request(request: Request, settings: Settings) -> bool:
    """Determine whether the request should use read-only demo data."""
    return (
        request.headers.get("X-BreatheMap-Demo") in ("true", "1") or settings.DEMO_MODE == "force"
    )


def _meta_envelope(is_demo: bool, warnings: list[str] | None = None) -> dict[str, Any]:
    """Build standard API metadata envelope."""
    now_iso = datetime.now(UTC).isoformat()
    return {
        "source": ["breathewatch-demo" if is_demo else "breathewatch-community"],
        "observed_at": now_iso,
        "fetched_at": now_iso,
        "is_demo": is_demo,
        "cached": False,
        "warnings": warnings or [],
    }


@router.get("/reports/nearby")
async def get_nearby_reports(
    request: Request,
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    radius_km: float = Query(REPORT_DEFAULT_RADIUS_KM, ge=0.1, le=REPORT_MAX_RADIUS_KM),
    hours: int = Query(REPORT_DEFAULT_HOURS, ge=1, le=48),
    category: str | None = Query(None),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """List nearby published, non-expired community reports."""
    ip = get_client_ip(request, is_production=settings.APP_ENV == "production")
    limiter.check_and_record(
        f"api:{hash_subject(ip, settings.APP_SECRET)}", API_RATE_LIMIT_PER_MINUTE, 60
    )

    is_demo = _is_demo_request(request, settings)
    service = ReportService(get_store(request))
    reports, warnings = await service.list_nearby(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        hours=hours,
        category=category,
        is_demo=is_demo,
    )
    return {
        "data": reports,
        "meta": _meta_envelope(is_demo=is_demo, warnings=warnings),
    }


@router.post("/reports")
async def create_report(
    body: CreateReportRequest,
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """Create a new community pollution report (or return existing duplicate)."""
    verify_same_origin(request, settings)
    ip = get_client_ip(request, is_production=settings.APP_ENV == "production")
    reporter_hash = hash_subject(ip, settings.APP_SECRET)
    limiter.check_and_record(f"api:{reporter_hash}", API_RATE_LIMIT_PER_MINUTE, 60)

    is_demo = _is_demo_request(request, settings)
    service = ReportService(get_store(request))
    result = await service.create_report(
        category=body.category,
        description=body.description,
        lat=body.lat,
        lon=body.lon,
        user_lat=body.user_lat,
        user_lon=body.user_lon,
        reporter_hash=reporter_hash,
        is_demo=is_demo,
    )
    return {
        "data": result,
        "meta": _meta_envelope(is_demo=is_demo),
    }


@router.post("/reports/{report_id}/confirm")
async def confirm_report(
    report_id: str,
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """Confirm an existing community report ('I see this too')."""
    verify_same_origin(request, settings)
    ip = get_client_ip(request, is_production=settings.APP_ENV == "production")
    reporter_hash = hash_subject(ip, settings.APP_SECRET)
    limiter.check_and_record(f"api:{reporter_hash}", API_RATE_LIMIT_PER_MINUTE, 60)

    is_demo = _is_demo_request(request, settings)
    service = ReportService(get_store(request))
    result = await service.confirm_report(
        report_id=report_id,
        reporter_hash=reporter_hash,
        is_demo=is_demo,
    )
    return {
        "data": result,
        "meta": _meta_envelope(is_demo=is_demo),
    }


@router.post("/reports/{report_id}/flag")
async def flag_report(
    report_id: str,
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """Flag a community report for moderation."""
    verify_same_origin(request, settings)
    ip = get_client_ip(request, is_production=settings.APP_ENV == "production")
    reporter_hash = hash_subject(ip, settings.APP_SECRET)
    limiter.check_and_record(f"api:{reporter_hash}", API_RATE_LIMIT_PER_MINUTE, 60)

    is_demo = _is_demo_request(request, settings)
    service = ReportService(get_store(request))
    result = await service.flag_report(
        report_id=report_id,
        reporter_hash=reporter_hash,
        is_demo=is_demo,
    )
    return {
        "data": result,
        "meta": _meta_envelope(is_demo=is_demo),
    }
