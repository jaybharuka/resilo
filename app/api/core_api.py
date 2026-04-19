from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.env_validator import validate_environment

validate_environment()

from app.api.remediation_jobs_runtime import build_remediation_jobs_router
from app.api.remediation_runtime import build_remediation_router
from app.api.runtime import (build_agents_router, build_alerts_router,
                             build_health_router, build_metrics_router,
                             build_stream_router)
from app.api.v1_api import build_v1_router
from app.api.intelligence_api import build_intelligence_router
from app.core.database import init_db, wait_for_db

metrics_router = build_metrics_router()
alerts_router = build_alerts_router()
agents_router = build_agents_router()
health_router = build_health_router()
stream_router = build_stream_router()
remediation_router = build_remediation_router()
remediation_jobs_router = build_remediation_jobs_router()
legacy_router = APIRouter()

router = APIRouter()
router.include_router(metrics_router)
router.include_router(alerts_router)
router.include_router(agents_router)
router.include_router(health_router)
router.include_router(stream_router)
router.include_router(remediation_router)
router.include_router(remediation_jobs_router)
router.include_router(build_v1_router())
router.include_router(build_intelligence_router())

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
    import logging, os
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig
    try:
        _ini = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
        if not os.path.exists(_ini):
            _ini = "alembic.ini"  # fallback: CWD
        cfg = AlembicConfig(_ini)
        alembic_command.upgrade(cfg, "head")
        logging.warning("[startup] alembic upgrade head OK")
    except Exception as exc:
        logging.error("[startup] alembic upgrade head FAILED: %s", exc)
    await wait_for_db()
    await init_db()
