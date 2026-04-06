"""SOC2-friendly structured audit logging."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.logger import get_logger

log = get_logger("audit")


class AuditService:
    @staticmethod
    async def write(
        db: AsyncSession,
        *,
        action: str,
        action_type: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> None:
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        await db.execute(
            text(
                """
                INSERT INTO audit_logs (
                    id, org_id, user_id, action, action_type, resource_type, resource_id,
                    detail, ip_address, user_agent, status, error_message, created_at
                ) VALUES (
                    :id, :org_id, :user_id, :action, :action_type, :resource_type, :resource_id,
                    :detail, :ip_address, :user_agent, :status, :error_message, :created_at
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "user_id": user_id,
                "action": action,
                "action_type": action_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "detail": detail,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "status": status,
                "error_message": error_message,
                "created_at": datetime.now(timezone.utc),
            },
        )

        log.info(
            "audit_event",
            extra={
                "action": action,
                "action_type": action_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "user_id": user_id,
                "org_id": org_id,
                "status": status,
                "ip_address": ip_address,
            },
        )


async def audit_log(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
    status: str = "success",
    error_message: Optional[str] = None,
) -> None:
    await AuditService.write(
        db,
        action=action,
        action_type=action.split(".")[0] if "." in action else "generic",
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        org_id=org_id,
        detail=detail,
        request=request,
        status=status,
        error_message=error_message,
    )
