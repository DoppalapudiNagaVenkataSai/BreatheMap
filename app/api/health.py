"""Health and system metadata endpoints."""

from typing import Any

from fastapi import APIRouter, Depends

from app.config import Settings
from app.constants import APP_NAME, APP_VERSION
from app.dependencies import get_app_settings

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
async def health_check(settings: Settings = Depends(get_app_settings)) -> dict[str, Any]:
    """Health check endpoint indicating active features and state."""
    features = {
        "gemini_enabled": settings.GEMINI_ENABLED and bool(settings.GEMINI_API_KEY),
        "routing_ors": bool(settings.ORS_API_KEY),
        "demo_mode": settings.DEMO_MODE,
        "store_backend": settings.STORE_BACKEND,
    }
    return {
        "data": {
            "status": "ok",
            "app": APP_NAME,
            "version": APP_VERSION,
            "features": features,
        }
    }


@router.get("/meta")
async def meta_info() -> dict[str, Any]:
    """Basic service provenance and metadata."""
    return {
        "data": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "primary_focus": "Estimated PM2.5 Inhalation Exposure Reduction",
        }
    }
