"""API tests for POST /api/v1/assistant/chat."""

import pytest
from httpx import AsyncClient

from app.api.assistant import get_gemini_client
from app.assistant.gemini_client import AssistantDraft, FakeGeminiClient
from app.config import Settings
from app.dependencies import get_app_settings
from app.main import app


@pytest.mark.asyncio
async def test_assistant_chat_demo_quick_mode(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/assistant/chat",
        headers={"X-BreatheMap-Demo": "1"},
        json={
            "message": "Going to New Delhi Railway Station at 10 PM, best way?",
            "context": {"lat": 28.6315, "lon": 77.2167},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["is_demo"] is True
    data = body["data"]
    assert data["answer_mode"] == "quick"
    assert any(c["type"] == "route_comparison" for c in data["cards"])


@pytest.mark.asyncio
async def test_assistant_chat_ai_enabled_with_fake_client(client: AsyncClient) -> None:
    fake = FakeGeminiClient(
        draft=AssistantDraft(
            summary="Modelled air quality data is shown in the summary card.",
            recommendation="Check the cleanest window before heading outdoors.",
            reasons=[],
            caveats=["Modelled data."],
            used_fact_ids=["F1"],
        )
    )
    test_settings = Settings(GEMINI_ENABLED=True, GEMINI_API_KEY="fake-key")
    app.dependency_overrides[get_app_settings] = lambda: test_settings
    app.dependency_overrides[get_gemini_client] = lambda: fake
    try:
        res = await client.post(
            "/api/v1/assistant/chat",
            headers={"X-BreatheMap-Demo": "1"},
            json={
                "message": "How's the air near me?",
                "context": {"lat": 28.6315, "lon": 77.2167},
            },
        )
        assert res.status_code == 200
        assert res.json()["data"]["answer_mode"] == "ai"
        assert fake.call_count == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_assistant_chat_validation_and_origin_check(client: AsyncClient) -> None:
    # Overlong message (> 500 chars) -> 422
    res_long = await client.post(
        "/api/v1/assistant/chat",
        json={"message": "x" * 501},
    )
    assert res_long.status_code == 422

    # Cross-origin POST -> 403
    res_origin = await client.post(
        "/api/v1/assistant/chat",
        headers={"Origin": "https://evil.attacker.com"},
        json={"message": "Hi"},
    )
    assert res_origin.status_code == 403
