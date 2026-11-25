"""Security tests for BreatheWatch reports, admin auth, origin checks, and XSS safety."""

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.dependencies import get_app_settings
from app.main import app


@pytest.mark.asyncio
async def test_injection_text_stored_as_plain_text(client: AsyncClient) -> None:
    payload = {
        "category": "smoke",
        "description": "<script>alert('xss')</script> burning plastic near the gate",
        "lat": 28.631,
        "lon": 77.217,
        "user_lat": 28.631,
        "user_lon": 77.217,
    }
    res = await client.post("/api/v1/reports", json=payload)
    assert res.status_code == 200
    rep = res.json()["data"]["report"]
    # Stored verbatim as plain text; never executed, and UI uses textContent
    assert rep["description"] == "<script>alert('xss')</script> burning plastic near the gate"
    assert "reporter_hash" not in rep


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_desc",
    [
        "Visit https://evil.example.com for more info",
        "Email me at victim@example.org right away",
        "Call +91 98765 43210 if you see this smoke",
    ],
)
async def test_privacy_rejects_urls_emails_phones(client: AsyncClient, bad_desc: str) -> None:
    res = await client.post(
        "/api/v1/reports",
        json={
            "category": "odour",
            "description": bad_desc,
            "lat": 28.631,
            "lon": 77.217,
            "user_lat": 28.631,
            "user_lon": 77.217,
        },
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_origin_check_blocks_cross_origin_post(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/reports",
        headers={"Origin": "https://evil.attacker.com"},
        json={
            "category": "smoke",
            "description": "Valid smoke description near the crossing.",
            "lat": 28.631,
            "lon": 77.217,
            "user_lat": 28.631,
            "user_lon": 77.217,
        },
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN_ORIGIN"


@pytest.mark.asyncio
async def test_admin_auth_unset_returns_404_and_invalid_returns_403(client: AsyncClient) -> None:
    # Unset ADMIN_TOKEN -> 404
    unset_settings = Settings(ADMIN_TOKEN=None)
    app.dependency_overrides[get_app_settings] = lambda: unset_settings
    try:
        res_404 = await client.post("/api/v1/admin/reports/any-id/hide")
        assert res_404.status_code == 404
    finally:
        app.dependency_overrides.clear()

    # Set ADMIN_TOKEN -> missing header returns 401, wrong token returns 403
    set_settings = Settings(ADMIN_TOKEN="correct-token")  # noqa: S106
    app.dependency_overrides[get_app_settings] = lambda: set_settings
    try:
        res_401 = await client.post("/api/v1/admin/reports/any-id/hide")
        assert res_401.status_code == 401

        res_403 = await client.post(
            "/api/v1/admin/reports/any-id/hide",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert res_403.status_code == 403
    finally:
        app.dependency_overrides.clear()
