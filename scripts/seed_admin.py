"""Idempotent PostgreSQL admin seed + login verification script."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Optional

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.env_validator import validate_environment

validate_environment()

DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", os.getenv("ADMIN_DEFAULT_EMAIL", "admin@company.local"))
DEFAULT_ADMIN_USERNAME = os.getenv("SEED_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD") or os.getenv("ADMIN_DEFAULT_PASSWORD")
DEFAULT_LOGIN_HOST = os.getenv("LOGIN_TEST_URL", "http://localhost:5000/auth/login")


async def seed_admin(email: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None) -> bool:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is missing")
        return False

    email = email or DEFAULT_ADMIN_EMAIL
    username = username or DEFAULT_ADMIN_USERNAME
    password = password or DEFAULT_ADMIN_PASSWORD

    engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        async with engine.begin() as conn:
            org_result = await conn.execute(text("SELECT id FROM organizations LIMIT 1"))
            org_row = org_result.fetchone()
            if org_row is None:
                import uuid

                org_id = str(uuid.uuid4())
                await conn.execute(
                    text(
                        "INSERT INTO organizations (id, name, slug, plan, is_active, created_at) "
                        "VALUES (:id, 'Default Organization', 'default', 'enterprise', true, NOW())"
                    ),
                    {"id": org_id},
                )
            else:
                org_id = org_row[0]

            user_result = await conn.execute(
                text("SELECT id FROM users WHERE email = :email OR username = :username"),
                {"email": email, "username": username},
            )
            user_row = user_result.fetchone()

            if user_row is None:
                import uuid

                user_id = str(uuid.uuid4())
                await conn.execute(
                    text(
                        "INSERT INTO users (id, org_id, email, username, hashed_password, role, "
                        "is_active, must_change_password, two_factor_enabled, created_at, updated_at) "
                        "VALUES (:id, :org_id, :email, :username, :pw, 'admin', true, false, false, NOW(), NOW())"
                    ),
                    {
                        "id": user_id,
                        "org_id": org_id,
                        "email": email,
                        "username": username,
                        "pw": pw_hash,
                    },
                )
                print(f"[OK] Admin created: {email}")
            else:
                await conn.execute(
                    text(
                        "UPDATE users SET hashed_password = :pw, is_active = true, must_change_password = false "
                        "WHERE id = :id"
                    ),
                    {"pw": pw_hash, "id": user_row[0]},
                )
                print(f"[OK] Admin updated: {email}")
        return True
    finally:
        await engine.dispose()


def verify_login(host: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None) -> bool:
    import json
    import urllib.request

    host = host or DEFAULT_LOGIN_HOST
    email = email or DEFAULT_ADMIN_EMAIL
    password = password or DEFAULT_ADMIN_PASSWORD
    normalized_host = host.rstrip("/")
    url = normalized_host if normalized_host.endswith("/auth/login") else f"{normalized_host}/auth/login"
    payload = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            body = json.loads(response.read())
        ok = bool(body.get("token") and body.get("refresh_token"))
        if ok:
            print("[OK] Login verification passed")
        else:
            print(f"[ERROR] Unexpected login payload: {body}")
        return ok
    except Exception as exc:
        print(f"[ERROR] Login verification failed: {exc}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--host", default=DEFAULT_LOGIN_HOST)
    parser.add_argument("--email", default=DEFAULT_ADMIN_EMAIL)
    parser.add_argument("--username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--password", default=DEFAULT_ADMIN_PASSWORD)
    args = parser.parse_args()

    if not args.check_only:
        seeded = asyncio.run(seed_admin(args.email, args.username, args.password))
        if not seeded:
            sys.exit(1)
        print()
    sys.exit(0 if verify_login(args.host, args.email, args.password) else 1)
