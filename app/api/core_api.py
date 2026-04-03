from __future__ import annotations

from fastapi import APIRouter, FastAPI

from config.env_validator import validate_environment

validate_environment()

from app.api.runtime import (
    build_agents_router,
    build_alerts_router,
    build_health_router,
    build_metrics_router,
    build_stream_router,
)
from app.core.database import init_db, wait_for_db

metrics_router = build_metrics_router()
alerts_router = build_alerts_router()
agents_router = build_agents_router()
health_router = build_health_router()
stream_router = build_stream_router()
legacy_router = APIRouter()

router = APIRouter()
router.include_router(metrics_router)
router.include_router(alerts_router)
router.include_router(agents_router)
router.include_router(health_router)
router.include_router(stream_router)

app = FastAPI(title="core_api")
app.include_router(router)
app.include_router(legacy_router)


@app.on_event("startup")
async def _startup() -> None:
    await wait_for_db()
    await init_db()
