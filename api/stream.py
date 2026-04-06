from __future__ import annotations

from fastapi import APIRouter

from app.api.core_api import stream_router as router  # noqa: F401

legacy_router = APIRouter()
