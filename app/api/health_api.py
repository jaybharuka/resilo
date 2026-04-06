from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(tags=["health"])


async def check_db_connectivity(db: AsyncSession) -> bool:
    await db.execute(text("SELECT 1"))
    return True


async def check_migrations_complete(db: AsyncSession) -> bool:
    result = await db.execute(text("SELECT version_num FROM alembic_version"))
    row = result.first()
    if row is None:
        return False
    return str(row[0]) == "004"


def get_diagnostics(database_ok: bool, migrations_ok: bool, latency_ms: int) -> dict[str, Any]:
    return {
        "status": "healthy" if database_ok else "degraded",
        "database": "connected" if database_ok else "unreachable",
        "migrations": "complete" if migrations_ok else "pending",
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/live")
async def health_live() -> dict[str, Any]:
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await check_db_connectivity(db)
        return {
            "status": "ready",
            "database": "connected",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "database": "unreachable",
                "error": str(exc),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ) from exc


@router.get("/health/startup")
async def health_startup(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        await check_db_connectivity(db)
        migrations_ok = await check_migrations_complete(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "error": str(exc)}) from exc

    if not migrations_ok:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "migrations": "pending",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    return {"status": "ready", "migrations": "complete", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/deep")
async def health_deep(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    started = time.perf_counter()
    database_ok = False
    migrations_ok = False

    try:
        database_ok = await check_db_connectivity(db)
        migrations_ok = await check_migrations_complete(db)
    except Exception:
        database_ok = False

    return get_diagnostics(database_ok, migrations_ok, int((time.perf_counter() - started) * 1000))
