from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditService
from app.core.database import get_db
from app.core.pricing import PricingService
from app.core.sso_handler import SSOHandler

router = APIRouter(prefix="/auth/sso", tags=["auth", "sso"])


class SSOLoginRequest(BaseModel):
    org_id: str = Field(..., min_length=36, max_length=36)


class SSOACSRequest(BaseModel):
    org_id: str = Field(..., min_length=36, max_length=36)
    saml_response: str = Field(..., min_length=1)
    relay_state: Optional[str] = None


@router.post("/login")
async def sso_login(body: SSOLoginRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    pricing = PricingService()
    enabled, reason = await pricing.check_sso_available(db, body.org_id)
    if not enabled:
        raise HTTPException(status_code=403, detail=reason)

    handler = SSOHandler()
    idp_url = await handler.get_idp_login_url(db, body.org_id)
    return {"provider": "okta", "org_id": body.org_id, "redirect_url": idp_url}


@router.post("/acs")
async def sso_acs(body: SSOACSRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    handler = SSOHandler()

    try:
        request_data = handler.build_request_data(request, body.saml_response, body.relay_state)
        user_info = await handler.verify_and_extract_saml_claims(
            db,
            org_id=body.org_id,
            request_data=request_data,
        )
        user = await handler.provision_or_link_user(db, user_info, org_id=body.org_id)
        token = handler.create_jwt_after_sso(user)

        await AuditService.write(
            db,
            action="auth.sso.login",
            action_type="authentication",
            resource_type="user",
            resource_id=user.id,
            user_id=user.id,
            org_id=user.org_id,
            detail={"email": user.email, "provider": "okta", "name_id": user_info.get("name_id")},
            status="success",
            request=request,
        )

        await db.commit()
    except ValueError as exc:
        await AuditService.write(
            db,
            action="auth.sso.login",
            action_type="authentication",
            resource_type="user",
            detail={"provider": "okta"},
            status="failed",
            error_message=str(exc),
            request=request,
        )
        await db.commit()
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return {
        "access_token": token,
        "token_type": "bearer",
        "org_id": user.org_id,
        "user_id": user.id,
        "role": user.role,
    }


@router.get("/metadata")
async def sso_metadata() -> dict[str, Any]:
    return {
        "entity_id": "https://resilo.local/auth/sso/metadata",
        "acs_url": "https://resilo.local/auth/sso/acs",
        "name_id_format": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        "provider": "okta",
    }
