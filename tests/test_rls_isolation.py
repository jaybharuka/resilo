from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt

from app.api.middleware.org_context import OrgContextMiddleware
from app.api.runtime import _require_org_access

JWT_SECRET = "phase4-test-secret"
ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(OrgContextMiddleware)

    @app.get("/api/protected")
    async def protected_endpoint() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/api/context")
    async def context_endpoint(request: Request) -> dict[str, str | None]:
        return {"org_id": getattr(request.state, "org_id", None)}

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "healthy"}

    return app


def test_rejects_protected_request_without_bearer() -> None:
    app = _build_app()
    client = TestClient(app)
    response = client.get("/api/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_rejects_token_without_org_id_claim() -> None:
    os.environ["JWT_SECRET_KEY"] = JWT_SECRET
    app = _build_app()
    client = TestClient(app)

    token = jwt.encode({"sub": "u1", "role": "employee", "type": "access"}, JWT_SECRET, algorithm="HS256")
    response = client.get("/api/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "org_id is required in JWT"


def test_rejects_cross_tenant_token_for_org_route(monkeypatch) -> None:
    os.environ["JWT_SECRET_KEY"] = JWT_SECRET

    async def _fake_payload(_token: str) -> dict[str, str]:
        return {"sub": "u1", "org_id": ORG_A, "role": "employee", "type": "access"}

    monkeypatch.setattr("app.api.runtime._require_valid_access_payload", _fake_payload)

    token = jwt.encode(
        {"sub": "u1", "org_id": ORG_A, "role": "employee", "type": "access"},
        JWT_SECRET,
        algorithm="HS256",
    )

    app = FastAPI()

    @app.get("/api/orgs/{org_id}/guard")
    async def org_guard(org_id: str, request: Request):
        await _require_org_access(request, org_id)
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        f"/api/orgs/{ORG_B}/guard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_concurrent_requests_do_not_leak_org_context() -> None:
    os.environ["JWT_SECRET_KEY"] = JWT_SECRET
    app = _build_app()
    client = TestClient(app)

    token_a = jwt.encode(
        {"sub": "u1", "org_id": ORG_A, "role": "employee", "type": "access"},
        JWT_SECRET,
        algorithm="HS256",
    )
    token_b = jwt.encode(
        {"sub": "u2", "org_id": ORG_B, "role": "employee", "type": "access"},
        JWT_SECRET,
        algorithm="HS256",
    )

    def call_context(token: str) -> str | None:
        response = client.get("/api/context", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        return response.json()["org_id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        org_a, org_b = pool.map(call_context, [token_a, token_b])

    assert org_a == ORG_A
    assert org_b == ORG_B


def test_public_health_is_not_blocked() -> None:
    app = _build_app()
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
