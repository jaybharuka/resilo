"""
rbac.py — Role-Based Access Control for AIOps Bot

Imported by both auth_api.py and core_api.py.
All permission checks happen here — endpoints never do ad-hoc role comparisons.

Roles:
    admin   — full access within org (users, agents, metrics, alerts, remediation)
    devops  — agents + metrics + alerts + remediation; no user management
    viewer  — read-only across all resources
    manager — alias for devops (legacy)
    employee— alias for viewer (legacy)
    guest   — no access (blocked at login check)

Usage in FastAPI routes:
    @router.get("/agents")
    async def list_agents(user=Depends(require_permission("agents:read"))):
        ...

    @router.delete("/agents/{id}")
    async def delete_agent(user=Depends(require_permission("agents:delete"))):
        ...
"""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, User, Agent

log = logging.getLogger("rbac")

JWT_SECRET    = os.getenv("JWT_SECRET_KEY")   # required — validated by validate_secrets() at service startup
JWT_ALGORITHM = "HS256"

bearer = HTTPBearer(auto_error=False)

# ── Permission matrix ─────────────────────────────────────────────────────────

_WILDCARD = {"*"}

ROLE_PERMISSIONS: dict[str, set] = {
    "admin": _WILDCARD,
    "devops": {
        "orgs:read",
        "agents:read", "agents:write", "agents:delete",
        "metrics:read",
        "alerts:read", "alerts:write",
        "remediation:read", "remediation:write", "remediation:execute",
        "audit:read",
    },
    "viewer": {
        "orgs:read",
        "agents:read",
        "metrics:read",
        "alerts:read",
        "remediation:read",
    },
    # Legacy role aliases
    "manager":  None,   # resolved below
    "employee": None,
    "guest":    set(),
}

# Resolve aliases
ROLE_PERMISSIONS["manager"]  = ROLE_PERMISSIONS["devops"]
ROLE_PERMISSIONS["employee"] = ROLE_PERMISSIONS["viewer"]


def has_permission(role: str, permission: str) -> bool:
    """Return True if `role` grants `permission`."""
    perms = ROLE_PERMISSIONS.get(role, set()) or set()
    if "*" in perms:
        return True
    # Wildcard namespace: "agents:*" grants "agents:read", "agents:write", etc.
    namespace = permission.split(":")[0]
    return permission in perms or f"{namespace}:*" in perms


# ── JWT token model ───────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub:      str
    email:    Optional[str] = None
    role:     str
    username: str = ""
    org_id:   Optional[str] = None
    type:     str = "access"


# ── Core auth dependencies ────────────────────────────────────────────────────

async def get_token_payload(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> TokenPayload:
    """Decode and validate the Bearer JWT. Returns TokenPayload. Does NOT hit DB."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not creds:
        raise exc
    try:
        raw = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Reject tokens explicitly typed as something other than access
        tok_type = raw.get("type")
        if tok_type and tok_type != "access":
            raise exc
        # Normalize legacy field names from auth_system.py
        if "sub" not in raw and "user_id" in raw:
            raw["sub"] = raw["user_id"]
        if "org_id" not in raw and "company_id" in raw:
            raw["org_id"] = raw["company_id"]
        if "username" not in raw and "email" in raw:
            raw["username"] = raw["email"].split("@")[0]
        return TokenPayload(**{k: v for k, v in raw.items() if k in TokenPayload.model_fields})
    except (JWTError, Exception):
        raise exc


async def get_current_user(
    token: TokenPayload = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the JWT sub → User row. Validates is_active."""
    result = await db.execute(select(User).where(User.id == token.sub))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


# ── Permission dependency factory ─────────────────────────────────────────────

def require_permission(permission: str) -> Callable:
    """
    Returns a FastAPI dependency that checks the JWT role against the permission.
    Example: Depends(require_permission("agents:write"))
    """
    async def _dep(
        token: TokenPayload = Depends(get_token_payload),
    ) -> TokenPayload:
        if not has_permission(token.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Insufficient permissions",
                    "required": permission,
                    "role": token.role,
                },
            )
        return token
    return _dep


def require_org(token_arg: str = "token") -> Callable:
    """
    Returns a dependency that validates the URL's org_id matches the JWT's org_id.
    Admins bypass this check (they may manage other orgs).

    Usage:
        async def my_endpoint(org_id: str, token=Depends(require_org_access)):
    """
    async def _dep(
        org_id: str,
        token: TokenPayload = Depends(get_token_payload),
    ) -> TokenPayload:
        if token.role == "admin":
            return token  # admins can access any org
        if not token.org_id:
            raise HTTPException(status_code=403, detail="No organization assigned to your account")
        if token.org_id != org_id:
            raise HTTPException(status_code=403, detail="Organization access denied")
        return token
    return _dep


# Convenience: combined permission + org check
def require(permission: str):
    """
    Combined dependency: checks permission AND org_id match.

    Usage:
        async def get_agents(org_id: str, token=Depends(require("agents:read"))):
    """
    async def _dep(
        org_id: str,
        token: TokenPayload = Depends(require_permission(permission)),
    ) -> TokenPayload:
        if token.role != "admin":
            if not token.org_id:
                raise HTTPException(status_code=403, detail="No organization assigned to your account")
            if token.org_id != org_id:
                raise HTTPException(status_code=403, detail="Organization access denied")
        return token
    return _dep


# ── Agent authentication ──────────────────────────────────────────────────────

def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def get_agent_from_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """
    Authenticate an agent via X-Agent-Key header.
    Updates agent.last_seen and agent.status = "online".

    Raises HTTP 401 if key is missing or invalid.
    """
    raw_key = request.headers.get("X-Agent-Key", "")
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Agent-Key header required",
            headers={"WWW-Authenticate": "X-Agent-Key"},
        )

    key_hash = _hash_key(raw_key)
    result = await db.execute(
        select(Agent).where(Agent.key_hash == key_hash, Agent.is_active == True)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent key")

    # Update liveness
    agent.last_seen = datetime.now(timezone.utc)
    agent.status = "online"
    await db.commit()

    return agent


def generate_agent_key() -> tuple[str, str]:
    """
    Generate a new agent API key.
    Returns (raw_key, key_hash).
    The raw_key is shown once to the admin; only key_hash is stored.
    """
    import secrets
    raw = secrets.token_urlsafe(40)
    return raw, _hash_key(raw)
