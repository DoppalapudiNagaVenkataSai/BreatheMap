"""Pytest configuration and shared test fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["APP_ENV"] = "test"
os.environ["APP_SECRET"] = "a" * 32
os.environ["STORE_BACKEND"] = "memory"
os.environ["DEMO_MODE"] = "allow"

from app.main import app
from app.storage.memory_store import MemoryStore


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client configured with the ASGI app."""
    # Ensure app state has storage and mock client for tests
    app.state.store = MemoryStore()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        app.state.http_client = ac
        yield ac
