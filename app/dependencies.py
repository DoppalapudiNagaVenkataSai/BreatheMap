"""Shared FastAPI dependencies for settings, clients, and storage."""

from typing import cast

import httpx
from fastapi import Request

from app.config import Settings, get_settings
from app.storage.memory_store import MemoryStore


def get_app_settings() -> Settings:
    """Dependency returning cached Settings."""
    return get_settings()


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency returning shared lifespan httpx.AsyncClient."""
    return cast(httpx.AsyncClient, request.app.state.http_client)


def get_store(request: Request) -> MemoryStore:
    """Dependency returning storage backend."""
    return cast(MemoryStore, request.app.state.store)
