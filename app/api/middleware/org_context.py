"""Middleware that extracts org_id from JWT and stores it in request context."""

from __future__ import annotations

import os
from typing import Callable
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.org_context import reset_current_org_id, set_current_org_id

JWT_ALGORITHM = "HS256"

_PUBLIC_PATH_PREFIXES = (
    "/auth/login",
    "/auth/refresh",
    "/auth/health",
    "/auth/sso/login",
    "/auth/sso/acs",
    "/auth/sso/metadata",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/ingest/heartbeat",
)


class OrgContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES):
            token = set_current_org_id(None)
            try:
                return await call_next(request)
            finally:
                reset_current_org_id(token)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing bearer token"})

        raw_token = auth_header.removeprefix("Bearer ").strip()
        jwt_secret = os.getenv("JWT_SECRET_KEY")
        if not jwt_secret:
            return JSONResponse(status_code=500, content={"detail": "JWT secret is not configured"})

        try:
            payload = jwt.decode(raw_token, jwt_secret, algorithms=[JWT_ALGORITHM])
        except JWTError:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})

        org_id = payload.get("org_id")
        if not org_id:
            return JSONResponse(status_code=403, content={"detail": "org_id is required in JWT"})

        try:
            UUID(str(org_id))
        except (TypeError, ValueError):
            return JSONResponse(status_code=403, content={"detail": "Invalid org_id in JWT"})

        request.state.org_id = str(org_id)
        token = set_current_org_id(str(org_id))
        try:
            return await call_next(request)
        finally:
            reset_current_org_id(token)
