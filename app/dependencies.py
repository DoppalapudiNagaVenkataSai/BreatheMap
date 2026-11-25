"""Shared FastAPI dependencies for settings, clients, and storage."""

from typing import cast

import httpx
from fastapi import Request

from app.config import Settings, get_settings
from app.storage.base import StoreProtocol
from app.storage.firestore_store import FirestoreStore
from app.storage.memory_store import MemoryStore


def get_app_settings() -> Settings:
    """Dependency returning cached Settings."""
    return get_settings()


def create_store(settings: Settings) -> StoreProtocol:
    """Create the configured storage backend (single instance per process)."""
    if settings.STORE_BACKEND == "firestore":
        return FirestoreStore.from_credentials_b64(
            settings.FIRESTORE_CREDENTIALS_B64,
            project_id=settings.FIREBASE_PROJECT_ID,
        )
    return MemoryStore()


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency returning shared lifespan httpx.AsyncClient."""
    return cast(httpx.AsyncClient, request.app.state.http_client)


def get_store(request: Request) -> StoreProtocol:
    """Dependency returning storage backend."""
    return cast(StoreProtocol, request.app.state.store)
