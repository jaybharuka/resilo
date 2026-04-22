"""
Unit tests for saas_features.py — no DB required.

Tests cover:
  - SignupRequest validation (password strength, username chars)
  - ForgotPasswordRequest / ResetPasswordRequest schemas
  - SupportRequest validation
  - _hash_token determinism
  - _hash_password format
  - _send_email mock path
  - Route registration on the FastAPI app
"""

import importlib
import os
import sys
import types

import pytest

# ── Minimal environment so env_validator doesn't block import ─────────────────

os.environ.setdefault("BACKUP_DIR", "/tmp")
os.environ.setdefault("DEPLOY_HOST", "localhost")
os.environ.setdefault("ADMIN_DEFAULT_EMAIL", "admin@test.com")
os.environ.setdefault("ADMIN_DEFAULT_PASSWORD", "Admin123!")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DEMO_MODE", "true")

from app.api.saas_features import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SignupRequest,
    SupportRequest,
    VerifyEmailRequest,
    _hash_password,
    _hash_token,
    _send_email,
)


# ── _hash_token ───────────────────────────────────────────────────────────────


def test_hash_token_deterministic() -> None:
    token = "abc123"
    assert _hash_token(token) == _hash_token(token)


def test_hash_token_length() -> None:
    h = _hash_token("sometoken")
    assert len(h) == 64  # SHA-256 hex digest


def test_hash_token_different_inputs() -> None:
    assert _hash_token("a") != _hash_token("b")


# ── _hash_password ────────────────────────────────────────────────────────────


def test_hash_password_format() -> None:
    h = _hash_password("MyPass1")
    assert h.startswith("pbkdf2_sha256$")
    parts = h.split("$")
    assert len(parts) == 4
    assert parts[1] == "260000"


def test_hash_password_unique_salts() -> None:
    h1 = _hash_password("SamePass1")
    h2 = _hash_password("SamePass1")
    assert h1 != h2  # different salts


# ── SignupRequest validation ──────────────────────────────────────────────────


def test_signup_valid() -> None:
    req = SignupRequest(email="user@example.com", username="alice", password="SecurePass1")
    assert req.username == "alice"
    assert req.email == "user@example.com"


def test_signup_username_lowercased() -> None:
    req = SignupRequest(email="u@example.com", username="Alice", password="SecurePass1")
    assert req.username == "alice"


def test_signup_password_needs_uppercase() -> None:
    with pytest.raises(Exception, match="uppercase"):
        SignupRequest(email="u@example.com", username="bob", password="nouppercase1")


def test_signup_password_needs_digit() -> None:
    with pytest.raises(Exception, match="digit"):
        SignupRequest(email="u@example.com", username="bob", password="NoDigitPass")


def test_signup_password_too_short() -> None:
    with pytest.raises(Exception):
        SignupRequest(email="u@example.com", username="bob", password="Ab1")


def test_signup_username_invalid_chars() -> None:
    with pytest.raises(Exception, match="Username"):
        SignupRequest(email="u@example.com", username="bad user!", password="SecurePass1")


def test_signup_invalid_email() -> None:
    with pytest.raises(Exception):
        SignupRequest(email="not-an-email", username="bob", password="SecurePass1")


# ── ResetPasswordRequest ──────────────────────────────────────────────────────


def test_reset_password_valid() -> None:
    req = ResetPasswordRequest(token="sometoken", new_password="NewPass1")
    assert req.token == "sometoken"


def test_reset_password_weak() -> None:
    with pytest.raises(Exception, match="uppercase"):
        ResetPasswordRequest(token="t", new_password="weakpass1")


# ── SupportRequest ────────────────────────────────────────────────────────────


def test_support_valid() -> None:
    req = SupportRequest(email="help@example.com", message="I need help with my account login.")
    assert req.email == "help@example.com"


def test_support_message_too_short() -> None:
    with pytest.raises(Exception):
        SupportRequest(email="help@example.com", message="hi")


def test_support_invalid_email() -> None:
    with pytest.raises(Exception):
        SupportRequest(email="notanemail", message="Some longer message here please.")


# ── _send_email mock mode ─────────────────────────────────────────────────────


def test_send_email_demo_mode_does_not_raise() -> None:
    os.environ["DEMO_MODE"] = "true"
    # Re-import to pick up env change (module caches DEMO_MODE at import time)
    import importlib
    import app.api.saas_features as sf
    original = sf.DEMO_MODE
    sf.DEMO_MODE = True
    try:
        _send_email("user@example.com", "Subject", "Body text")
    finally:
        sf.DEMO_MODE = original


# ── Route registration ────────────────────────────────────────────────────────


def test_all_routes_registered() -> None:
    from app.api.auth_api import app

    paths = {r.path for r in app.routes if hasattr(r, "path")}
    expected = {
        "/auth/signup",
        "/auth/forgot-password",
        "/auth/reset-password",
        "/auth/verify-email",
        "/auth/resend-verification",
        "/support",
        "/api/orgs/{org_id}/events",
        "/auth/login",
        "/auth/me",
        "/auth/refresh",
        "/auth/logout",
        "/auth/health",
    }
    missing = expected - paths
    assert not missing, f"Missing routes: {missing}"
