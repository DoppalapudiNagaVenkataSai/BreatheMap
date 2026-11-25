"""Test health and metadata endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    assert data["app"] == "BreatheMap"
    assert "features" in data


@pytest.mark.asyncio
async def test_meta_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/meta")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "version" in data
    assert "primary_focus" in data
