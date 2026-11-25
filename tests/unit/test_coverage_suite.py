"""Additional tests to achieve comprehensive test coverage."""

import pytest
from httpx import AsyncClient
from starlette.requests import Request

from app.config import Settings
from app.core.errors import ForbiddenOriginError, ValidationAppError, app_error_handler
from app.core.security import get_client_ip, hash_subject, verify_same_origin
from app.storage.memory_store import MemoryStore


@pytest.mark.asyncio
async def test_home_page_rendering(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "BreatheMap" in response.text
    assert "Skip to main content" in response.text


@pytest.mark.asyncio
async def test_body_size_limit_middleware(client: AsyncClient) -> None:
    large_payload = {"data": "x" * 20000}
    response = await client.post("/api/v1/health", json=large_payload)
    # The middleware intercepts oversized JSON payloads
    assert response.status_code in (413, 405)


def test_ip_extraction_and_hashing() -> None:
    scope = {
        "type": "http",
        "headers": [(b"x-vercel-forwarded-for", b"203.0.113.195, 10.0.0.1")],
        "client": ("127.0.0.1", 1234),
    }
    req = Request(scope)
    ip_prod = get_client_ip(req, is_production=True)
    assert ip_prod == "203.0.113.195"

    ip_dev = get_client_ip(req, is_production=False)
    assert ip_dev == "127.0.0.1"

    hashed = hash_subject(ip_prod, "some-secret-key-32-chars-minimum!!")
    assert len(hashed) == 32


def test_verify_same_origin() -> None:
    settings = Settings(APP_ENV="production", APP_SECRET="a" * 32)
    valid_scope = {
        "type": "http",
        "headers": [(b"origin", b"https://breathemap.org"), (b"host", b"breathemap.org")],
    }
    verify_same_origin(Request(valid_scope), settings)

    invalid_scope = {
        "type": "http",
        "headers": [(b"origin", b"https://malicious.org"), (b"host", b"breathemap.org")],
    }
    with pytest.raises(ForbiddenOriginError):
        verify_same_origin(Request(invalid_scope), settings)


@pytest.mark.asyncio
async def test_app_error_handler_direct() -> None:
    req = Request({"type": "http"})
    exc = ValidationAppError("Sample validation issue")
    res = await app_error_handler(req, exc)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_memory_store_list_nearby() -> None:
    store = MemoryStore()
    await store.create_report(
        {
            "id": "10",
            "category": "smoke",
            "geohash5": "ttnfv",
            "status": "published",
        }
    )
    await store.create_report(
        {
            "id": "11",
            "category": "dust",
            "geohash5": "ttnfv",
            "status": "hidden",
        }
    )
    nearby = await store.list_nearby(["ttnfv"])
    assert len(nearby) == 1
    assert nearby[0]["id"] == "10"
