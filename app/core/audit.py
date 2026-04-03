"""
Audit logging for sensitive operations.

Logs all user actions that modify data or access sensitive resources.
Includes user_id, org_id, action, resource_type, resource_id, IP, user_agent.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request
from logging_config import get_logger

log = get_logger("audit")


async def audit_log(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """
    Log a sensitive operation to the audit_logs table.
    
    Args:
        db: AsyncSession for database access
        action: Action performed (e.g., "user_created", "password_reset", "invite_accepted")
        resource_type: Type of resource (e.g., "user", "organization", "invite")
        resource_id: ID of the resource affected
        user_id: ID of the user performing the action
        org_id: ID of the organization context
        detail: Additional details as JSON (e.g., {"email": "user@example.com", "role": "admin"})
        request: FastAPI Request object to extract IP and user_agent
    """
    from database import AuditLog
    import uuid
    
    ip_address = None
    user_agent = None
    
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
    
    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(audit_entry)
    
    # Log to structured logs as well
    log.info(
        f"Audit: {action}",
        extra={
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id,
            "org_id": org_id,
            "ip_address": ip_address,
        },
    )
