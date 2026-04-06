from __future__ import annotations

from fastapi import APIRouter

from app.api.auth_api import router  # noqa: F401

legacy_router = APIRouter()
