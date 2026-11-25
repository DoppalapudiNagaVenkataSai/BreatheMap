"""End-to-end API scenario test in demo mode: air -> route -> assistant -> reports."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_e2e_demo_user_journey(client: AsyncClient) -> None:
    demo_headers = {"X-BreatheMap-Demo": "1"}

    # 1. Health check
    health = await client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["data"]["status"] == "ok"

    # 2. Air quality snapshot (demo)
    air_res = await client.get(
        "/api/v1/air?lat=28.6315&lon=77.2167&scale=naqi", headers=demo_headers
    )
    assert air_res.status_code == 200
    air_data = air_res.json()["data"]
    assert air_data["provenance"]["is_demo"] is True
    assert air_data["windows"]["cleanest"] is not None

    # 3. BreatheRoute multi-mode comparison (demo)
    route_res = await client.post(
        "/api/v1/routes/compare",
        headers=demo_headers,
        json={
            "origin": {"lat": 28.6315, "lon": 77.2167},
            "destination": {"lat": 28.6129, "lon": 77.2295},
            "modes": ["walk", "cycle", "car", "metro"],
        },
    )
    assert route_res.status_code == 200
    route_data = route_res.json()["data"]
    assert len(route_data["options"]) >= 4
    assert len(route_data["reports_along_route"]) >= 1

    # 4. 5-step AI Assistant demo conversation (Quick mode offline)
    steps = [
        ("Is it OK to jog at 6 PM for 40 minutes?", "activity_advice"),
        ("I'm going to New Delhi Railway Station at 10 PM — best way?", "route_comparison"),
        ("How do I keep the air cleaner at home?", "home_tips"),
        ("Any smoke reported near me?", "reports"),
        ("What does NAQI mean?", "glossary"),
    ]
    for msg, expected_card in steps:
        chat_res = await client.post(
            "/api/v1/assistant/chat",
            headers=demo_headers,
            json={"message": msg, "context": {"lat": 28.6315, "lon": 77.2167}},
        )
        assert chat_res.status_code == 200
        chat_data = chat_res.json()["data"]
        assert any(c["type"] == expected_card for c in chat_data["cards"])

    # 5. BreatheWatch nearby reports (demo read-only)
    watch_res = await client.get(
        "/api/v1/reports/nearby?lat=28.6315&lon=77.2167&radius_km=5&hours=24",
        headers=demo_headers,
    )
    assert watch_res.status_code == 200
    assert len(watch_res.json()["data"]) >= 3
