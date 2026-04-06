"""Pricing enforcement service for plan-gated operations."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Agent, Organization


class PricingService:
    """Service-level pricing checks with row locks for safe concurrent updates."""

    async def check_service_limit(self, db: AsyncSession, org_id: str) -> tuple[bool, Optional[str]]:
        org_stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = (await db.execute(org_stmt)).scalar_one_or_none()
        if org is None:
            return False, "Organization not found"

        plan = (org.plan or "starter").lower()
        plan_result = await db.execute(
            text("SELECT service_limit, sso_enabled FROM pricing_plans WHERE name = :name"),
            {"name": plan},
        )
        row = plan_result.first()
        if row is None:
            return False, f"Unknown plan: {org.plan}"

        service_limit = row[0]
        sso_enabled = bool(row[1])
        service_count = int((await db.execute(select(func.count(Agent.id)).where(Agent.org_id == org_id))).scalar_one() or 0)

        org.service_count = service_count
        org.service_limit = service_limit
        org.sso_enabled = sso_enabled

        if service_limit is not None and service_count >= service_limit:
            return False, f"Plan limit reached ({service_count}/{service_limit})"
        return True, None

    async def check_sso_available(self, db: AsyncSession, org_id: str) -> tuple[bool, Optional[str]]:
        org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
        if org is None:
            return False, "Organization not found"

        row = (
            await db.execute(
                text("SELECT sso_enabled FROM pricing_plans WHERE name = :name"),
                {"name": (org.plan or "starter").lower()},
            )
        ).first()
        if row is None:
            return False, f"Unknown plan: {org.plan}"
        if not bool(row[0]):
            return False, "SSO requires Enterprise plan"
        return True, None

    async def ensure_service_limit(self, db: AsyncSession, org_id: str) -> None:
        allowed, error = await self.check_service_limit(db, org_id)
        if not allowed:
            raise HTTPException(status_code=403, detail=error)
