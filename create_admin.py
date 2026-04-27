#!/usr/bin/env python3
"""Create or reseed default admin user in PostgreSQL."""

from __future__ import annotations

import asyncio

from config.env_validator import validate_environment

validate_environment()

from app.api.runtime import seed_admin_user
from app.core.database import init_db, wait_for_db


async def main() -> None:
    await wait_for_db()
    await init_db()
    await seed_admin_user()
    print("[OK] Default admin ensured in PostgreSQL.")


if __name__ == "__main__":
    asyncio.run(main())
