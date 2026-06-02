from __future__ import annotations

import os, pathlib
try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).parent.parent.parent / ".env", override=False)
except ImportError:
    pass

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.env_validator import validate_environment

validate_environment()

from app.api.remediation_jobs_runtime import build_remediation_jobs_router
from app.api.remediation_runtime import build_remediation_router
from app.api.runtime import (build_agents_router, build_alerts_router,
                             build_auth_router, build_health_router,
                             build_metrics_router, build_stream_router)
from app.api.v1_api import build_v1_router
from app.api.intelligence_api import build_intelligence_router
from app.api.prometheus_bridge import build_prometheus_router
from app.api.investigations_api import router as investigations_router
from app.core.database import init_db, wait_for_db

metrics_router = build_metrics_router()
alerts_router = build_alerts_router()
agents_router = build_agents_router()
auth_router = build_auth_router()
health_router = build_health_router()
stream_router = build_stream_router()
remediation_router = build_remediation_router()
remediation_jobs_router = build_remediation_jobs_router()
legacy_router = APIRouter()

router = APIRouter()
router.include_router(metrics_router)
router.include_router(alerts_router)
router.include_router(agents_router)
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(stream_router)
router.include_router(remediation_router)
router.include_router(remediation_jobs_router)
router.include_router(build_v1_router())
router.include_router(build_intelligence_router())
router.include_router(build_prometheus_router())
router.include_router(investigations_router)

app = FastAPI(title="core_api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(legacy_router)


@app.on_event("startup")
async def _startup() -> None:
    import logging
    from sqlalchemy import text
    from app.core.database import engine
    await wait_for_db()
    await init_db()
    # Ensure extended metric columns exist (idempotent — ADD COLUMN IF NOT EXISTS)
    _cols = [
        ("top_processes",   "JSON"),
        ("swap_percent",    "FLOAT"),
        ("swap_used_gb",    "FLOAT"),
        ("disk_read_mbps",  "FLOAT"),
        ("disk_write_mbps", "FLOAT"),
        ("net_established", "INTEGER"),
        ("net_close_wait",  "INTEGER"),
        ("net_time_wait",   "INTEGER"),
        ("load_avg_1m",     "FLOAT"),
        ("load_avg_5m",     "FLOAT"),
        ("load_avg_15m",    "FLOAT"),
        ("uptime_hours",    "FLOAT"),
        ("battery_percent", "FLOAT"),
        ("battery_plugged", "BOOLEAN"),
        ("disk_partitions", "JSON"),
    ]
    try:
        async with engine.begin() as conn:
            for col, typ in _cols:
                await conn.execute(text(
                    f"ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS {col} {typ}"
                ))
            await conn.execute(text(
                "ALTER TABLE alert_records ADD COLUMN IF NOT EXISTS resolution_reason TEXT"
            ))
            await conn.execute(text(
                "ALTER TABLE agent_action_log ADD COLUMN IF NOT EXISTS metadata_json TEXT"
            ))
            await conn.execute(text(
                "ALTER TABLE agents ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(20) DEFAULT 'dry_run'"
            ))
            await conn.execute(text(
                "ALTER TABLE agents ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'agent'"
            ))
            await conn.execute(text(
                "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_confidence_threshold FLOAT"
            ))
        logging.warning("[startup] schema columns ensured OK")
    except Exception as exc:
        logging.error("[startup] schema ensure FAILED: %s", exc)

    try:
        from app.api.runtime import (restore_ai_history_from_db,
                                     restore_exec_modes_from_db,
                                     restore_feedback_from_db)
        await restore_ai_history_from_db()
        await restore_exec_modes_from_db()
        await restore_feedback_from_db()
    except Exception as exc:
        logging.warning("[startup] in-memory state restore failed: %s", exc)
