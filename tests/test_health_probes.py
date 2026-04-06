from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health_api import router as health_router


def test_health_live_endpoint() -> None:
    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)

    response = client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert "timestamp" in payload
