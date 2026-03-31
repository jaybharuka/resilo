#!/usr/bin/env python3
"""
Reset admin@company.local password in PostgreSQL.

Usage:
    python reset_admin_password.py                   # sets Admin@1234
    python reset_admin_password.py --password <pw>   # custom password
"""
import asyncio
import os
import sys
import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set. Add it to your .env file.", file=sys.stderr)
    sys.exit(1)

ADMIN_EMAIL = "admin@company.local"


async def reset(new_password: str) -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12)).decode()

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": ADMIN_EMAIL},
        )
        row = result.fetchone()

        if not row:
            # Create the admin user from scratch
            import uuid
            # Ensure org exists
            org_r = await conn.execute(text("SELECT id FROM organizations LIMIT 1"))
            org_row = org_r.fetchone()
            if not org_row:
                org_id = str(uuid.uuid4())
                await conn.execute(text(
                    "INSERT INTO organizations (id, name, slug, plan, is_active, created_at) "
                    "VALUES (:id, 'Default Organization', 'default', 'enterprise', true, NOW())"
                ), {"id": org_id})
            else:
                org_id = org_row[0]

            user_id = str(uuid.uuid4())
            await conn.execute(text(
                "INSERT INTO users (id, org_id, email, username, hashed_password, role, "
                "is_active, must_change_password, two_factor_enabled, created_at, updated_at) "
                "VALUES (:id, :org_id, :email, 'admin', :pw, 'admin', true, false, false, NOW(), NOW())"
            ), {"id": user_id, "org_id": org_id, "email": ADMIN_EMAIL, "pw": hashed})
            print(f"[OK] Admin user created.")
        else:
            await conn.execute(
                text("UPDATE users SET hashed_password = :pw, must_change_password = false "
                     "WHERE email = :email"),
                {"pw": hashed, "email": ADMIN_EMAIL},
            )
            # Revoke all existing sessions
            await conn.execute(
                text("UPDATE user_sessions SET is_revoked = true WHERE user_id = :uid"),
                {"uid": row[0]},
            )
            print(f"[OK] Password reset. All existing sessions revoked.")

    await engine.dispose()
    print(f"    Email   : {ADMIN_EMAIL}")
    print(f"    Password: {new_password}")
    print(f"\nRestart auth_api and log in with the new password.")


if __name__ == "__main__":
    if "--password" in sys.argv:
        idx = sys.argv.index("--password")
        pw = sys.argv[idx + 1]
    else:
        pw = os.getenv("ADMIN_DEFAULT_PASSWORD")
        if not pw:
            print(
                "ERROR: No password provided. Either pass --password <pw> or set "
                "ADMIN_DEFAULT_PASSWORD in your .env file.",
                file=sys.stderr,
            )
            sys.exit(1)

    if len(pw) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)

    asyncio.run(reset(pw))
