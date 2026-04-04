"""
tests/helpers.py — Shared utilities for test modules.

Importable by test files; conftest.py also references make_jwt.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Ensure app packages are on sys.path ──────────────────────────────────────
_root = Path(__file__).resolve().parent.parent
for _p in [
    str(_root),
    str(_root / "app"),
    str(_root / "app" / "api"),
    str(_root / "app" / "core"),
    str(_root / "app" / "auth"),
    str(_root / "app" / "analytics"),
    str(_root / "app" / "integrations"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

_TEST_JWT_SECRET = os.environ.get(
    "JWT_SECRET_KEY",
    "test-jwt-secret-for-pytest-only-not-for-production-use",
)

# Set by conftest._setup_database after the admin user is seeded.
# Using the real admin user ID ensures tokens pass the DB-lookup in
# _require_valid_access_payload (which rejects tokens whose sub has no DB row).
_TEST_ADMIN_ID: str | None = None


def make_jwt(sub: str, role: str, org_id: str, email: str = "test@test.local") -> str:
    """Mint a signed HS256 JWT accepted by core_api's require() dependency."""
    from jose import jwt as _jose_jwt

    payload = {
        "sub": sub,
        "role": role,
        "org_id": org_id,
        "email": email,
        "username": email.split("@")[0],
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return _jose_jwt.encode(payload, _TEST_JWT_SECRET, algorithm="HS256")


def admin_jwt(org_id: str) -> str:
    """Convenience wrapper: admin-role JWT for org_id.

    Uses the real seeded admin user ID (populated by conftest) so the token
    passes the DB user-existence check in _require_valid_access_payload.
    Falls back to a random UUID when called outside a test session.
    """
    return make_jwt(sub=_TEST_ADMIN_ID or str(uuid.uuid4()), role="admin", org_id=org_id)
