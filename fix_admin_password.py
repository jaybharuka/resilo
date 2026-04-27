#!/usr/bin/env python3
"""PostgreSQL admin password reset utility."""

from __future__ import annotations

import asyncio
import os
import sys

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_EMAIL = os.getenv("ADMIN_DEFAULT_EMAIL", "admin@company.local")


async def reset_admin_password(password: str) -> bool:
    """Reset admin password directly in PostgreSQL."""
    if not password:
        raise ValueError("password is required — pass it as an argument or set ADMIN_DEFAULT_PASSWORD env var")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is missing")
        return False

    engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

        async with engine.begin() as conn:
            result = await conn.execute(
                text("UPDATE users SET hashed_password = :pw WHERE email = :email"),
                {"pw": pw_hash, "email": ADMIN_EMAIL},
            )
            rows_updated = result.rowcount or 0
            await conn.execute(
                text(
                    "UPDATE user_sessions SET is_revoked = true "
                    "WHERE user_id IN (SELECT id FROM users WHERE email = :email)"
                ),
                {"email": ADMIN_EMAIL},
            )

        if rows_updated > 0:
            print("[OK] Admin password updated successfully")
            print("  Username: admin")
            print(f"  Email: {ADMIN_EMAIL}")
            return True

        print("[ERROR] Admin user not found in database")
        return False
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    password = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ADMIN_DEFAULT_PASSWORD")
    if not password:
        print("Usage: fix_admin_password.py <new_password>")
        print("  or set ADMIN_DEFAULT_PASSWORD env var")
        sys.exit(1)
    success = asyncio.run(reset_admin_password(password=password))
    sys.exit(0 if success else 1)
