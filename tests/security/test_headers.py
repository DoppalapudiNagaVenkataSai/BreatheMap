"""Test security headers and request-id propagation."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    headers = response.headers

    assert "content-security-policy" in headers
    assert "x-content-type-options" in headers
    assert headers["x-content-type-options"] == "nosniff"
    assert "referrer-policy" in headers
    assert "permissions-policy" in headers
    assert "cross-origin-opener-policy" in headers
    assert "x-request-id" in headers


@pytest.mark.asyncio
async def test_custom_request_id_preserved(client: AsyncClient) -> None:
    custom_id = "test-request-id-12345"
    response = await client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert response.headers["x-request-id"] == custom_id
