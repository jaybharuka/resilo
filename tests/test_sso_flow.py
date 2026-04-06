from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth_sso_api import router as sso_router
from app.core import sso_handler as sso_handler_module
from app.core.database import User
from app.core.sso_handler import SSOHandler


@pytest.mark.asyncio
async def test_sso_parse_payload_requires_email() -> None:
    handler = SSOHandler()
    with pytest.raises(ValueError, match="missing email"):
        await handler.parse_acs_payload({"name_id": "abc", "signature_valid": True})


@pytest.mark.asyncio
async def test_sso_parse_payload_success() -> None:
    handler = SSOHandler()
    payload = {
        "email": "alice@example.com",
        "name_id": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Doe",
        "signature_valid": True,
        "assertion_id": "assertion-success-1",
    }
    result = await handler.parse_acs_payload(payload)
    assert result["email"] == "alice@example.com"
    assert result["name_id"] == "alice@example.com"


@pytest.mark.asyncio
async def test_sso_rejects_invalid_signature() -> None:
    handler = SSOHandler()
    payload = {
        "email": "alice@example.com",
        "name_id": "alice@example.com",
        "signature_valid": False,
    }
    with pytest.raises(ValueError, match="Invalid SAML signature"):
        await handler.parse_acs_payload(payload)


@pytest.mark.asyncio
async def test_sso_rejects_replay_assertion() -> None:
    handler = SSOHandler()
    payload = {
        "email": "alice@example.com",
        "name_id": "alice@example.com",
        "assertion_id": "assertion-replay-1",
        "signature_valid": True,
    }
    await handler.parse_acs_payload(payload)
    with pytest.raises(ValueError, match="replay"):
        await handler.parse_acs_payload(payload)


@pytest.mark.asyncio
async def test_sso_rejects_expired_assertion() -> None:
    handler = SSOHandler()
    payload = {
        "email": "alice@example.com",
        "name_id": "alice@example.com",
        "signature_valid": True,
        "not_on_or_after": "2000-01-01T00:00:00+00:00",
    }
    with pytest.raises(ValueError, match="expired"):
        await handler.parse_acs_payload(payload)


def test_jwt_after_sso_requires_org_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    handler = SSOHandler()
    user = User(
        id="user-1",
        org_id=None,
        email="alice@example.com",
        username="alice",
        hashed_password="sso_only",
        role="employee",
        is_active=True,
        must_change_password=False,
    )
    with pytest.raises(ValueError, match="missing org_id"):
        handler.create_jwt_after_sso(user)


def test_invalid_saml_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyDB:
        async def commit(self) -> None:
            return None

    async def _fake_db_dep():
        yield _DummyDB()

    async def _audit_noop(*args, **kwargs) -> None:
        return None

    async def _raise_invalid_signature(*args, **kwargs):
        raise ValueError("Invalid SAML signature")

    app = FastAPI()
    app.include_router(sso_router)

    from app.api.auth_sso_api import get_db

    app.dependency_overrides[get_db] = _fake_db_dep
    monkeypatch.setattr("app.api.auth_sso_api.AuditService.write", _audit_noop)
    monkeypatch.setattr(sso_handler_module.SSOHandler, "verify_and_extract_saml_claims", _raise_invalid_signature)

    client = TestClient(app)
    response = client.post(
        "/auth/sso/acs",
        json={
            "org_id": "11111111-1111-1111-1111-111111111111",
            "saml_response": "tampered-signature",
        },
    )

    assert response.status_code in (401, 403)
