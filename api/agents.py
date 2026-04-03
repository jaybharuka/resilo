from __future__ import annotations

from fastapi import APIRouter

from app.api.core_api import agents_router as router

legacy_router = APIRouter()
