from __future__ import annotations

from fastapi import APIRouter, FastAPI

from config.env_validator import validate_environment

validate_environment()

from app.api.runtime import build_auth_router, build_oauth_router, seed_admin_user
from app.core.database import init_db, wait_for_db

router       = build_auth_router()
oauth_router = build_oauth_router()
legacy_router = APIRouter()

app = FastAPI(title="auth_api")
app.include_router(router)
app.include_router(oauth_router)
app.include_router(legacy_router)


async def _seed_admin() -> None:
    await seed_admin_user()


@app.on_event("startup")
async def _startup() -> None:
    await wait_for_db()
    await init_db()
    await _seed_admin()
