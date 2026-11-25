"""API integration tests for BreatheWatch reports, admin moderation, and route integration."""

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.config import Settings, get_settings
from app.dependencies import create_store, get_app_settings
from app.main import app
from app.storage.memory_store import MemoryStore


@pytest.mark.asyncio
async def test_reports_lifecycle_create_nearby_confirm_flag(client: AsyncClient) -> None:
    payload = {
        "category": "open_burning",
        "description": "Roadside dry leaves burning near Connaught Place outer circle.",
        "lat": 28.6315,
        "lon": 77.2167,
        "user_lat": 28.632,
        "user_lon": 77.217,
    }
    create_res = await client.post("/api/v1/reports", json=payload)
    assert create_res.status_code == 200
    body = create_res.json()
    report_id = body["data"]["report"]["id"]
    assert body["data"]["duplicate_of"] is None
    assert body["meta"]["is_demo"] is False

    # Nearby query finds it
    nearby_res = await client.get(
        "/api/v1/reports/nearby?lat=28.6315&lon=77.2167&radius_km=3&hours=24"
    )
    assert nearby_res.status_code == 200
    items = nearby_res.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == report_id
    assert items[0]["status_label"] == "Unverified community report"

    # Confirm increments confirmations
    conf_res = await client.post(f"/api/v1/reports/{report_id}/confirm")
    assert conf_res.status_code == 200
    assert conf_res.json()["data"]["confirmations"] == 1

    # Flagging once leaves published
    flag_res = await client.post(f"/api/v1/reports/{report_id}/flag")
    assert flag_res.status_code == 200
    assert flag_res.json()["data"]["status"] == "published"


@pytest.mark.asyncio
async def test_reports_demo_mode_read_only(client: AsyncClient) -> None:
    res = await client.get(
        "/api/v1/reports/nearby?lat=28.6315&lon=77.2167&radius_km=5&hours=24",
        headers={"X-BreatheMap-Demo": "1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["meta"]["is_demo"] is True
    assert len(data["data"]) >= 3

    post_res = await client.post(
        "/api/v1/reports",
        headers={"X-BreatheMap-Demo": "1"},
        json={
            "category": "smoke",
            "description": "Trying to post in demo mode should fail.",
            "lat": 28.631,
            "lon": 77.217,
            "user_lat": 28.631,
            "user_lon": 77.217,
        },
    )
    assert post_res.status_code == 422
    assert "sample-data mode" in post_res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_route_compare_includes_reports_along_route(client: AsyncClient) -> None:
    # Demo routes go from Connaught Place (28.6315, 77.2167) to India Gate (28.6129, 77.2295)
    # Demo report demo-rep-2 is at (28.625, 77.219), right along Janpath!
    res = await client.post(
        "/api/v1/routes/compare",
        headers={"X-BreatheMap-Demo": "1"},
        json={
            "origin": {"lat": 28.6315, "lon": 77.2167},
            "destination": {"lat": 28.6129, "lon": 77.2295},
            "modes": ["walk"],
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data["reports_along_route"]) >= 1
    assert any(
        r["status_label"] == "Unverified community report" for r in data["reports_along_route"]
    )


@pytest.mark.asyncio
async def test_admin_hide_report(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Create report first
    create_res = await client.post(
        "/api/v1/reports",
        json={
            "category": "smoke",
            "description": "Thick black smoke near the main bus terminal.",
            "lat": 28.631,
            "lon": 77.217,
            "user_lat": 28.631,
            "user_lon": 77.217,
        },
    )
    rid = create_res.json()["data"]["report"]["id"]

    # Override settings with ADMIN_TOKEN
    test_settings = Settings(ADMIN_TOKEN="super-secret-admin-token")  # noqa: S106
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_app_settings] = lambda: test_settings
    try:
        hide_res = await client.post(
            f"/api/v1/admin/reports/{rid}/hide",
            headers={"Authorization": "Bearer super-secret-admin-token"},
        )
        assert hide_res.status_code == 200
        assert hide_res.json()["data"]["status"] == "hidden"

        # Should no longer appear in nearby
        nearby_res = await client.get("/api/v1/reports/nearby?lat=28.631&lon=77.217")
        assert nearby_res.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


def test_create_store_selects_memory_by_default() -> None:
    s = Settings(STORE_BACKEND="memory")
    store = create_store(s)
    assert isinstance(store, MemoryStore)


def test_demo_reports_file_is_valid_json() -> None:
    demo_path = Path("data/demo/delhi_reports.json")
    items: list[dict[str, Any]] = json.loads(demo_path.read_text(encoding="utf-8"))
    assert 6 <= len(items) <= 8
    assert all(item.get("is_demo") is True for item in items)
