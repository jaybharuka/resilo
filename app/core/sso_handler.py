"""SAML SSO handling with org mapping and JWT issuance."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import jwt
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Organization, User


class SSOHandler:
    _seen_assertions: dict[str, datetime] = {}

    def __init__(self) -> None:
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", "")
        self.jwt_algorithm = "HS256"
        self.access_ttl = int(os.getenv("JWT_ACCESS_TTL", "86400"))

    async def get_idp_login_url(self, db: AsyncSession, org_id: str) -> str:
        row = (
            await db.execute(
                """
                SELECT metadata_url
                FROM sso_configurations
                WHERE org_id = :org_id AND enabled = true
                """,
                {"org_id": org_id},
            )
        ).first()
        if row and row[0]:
            return row[0]
        return f"https://example.okta.com/app/{org_id}/sso/saml"

    async def parse_acs_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Legacy parser for already validated claims only.
        signature_valid = payload.get("signature_valid")
        if signature_valid is not True:
            raise ValueError("Invalid SAML signature")

        assertion_id = (payload.get("assertion_id") or "").strip()
        if assertion_id:
            self._evict_stale_assertions()
            if assertion_id in self._seen_assertions:
                raise ValueError("SAML assertion replay detected")
            self._seen_assertions[assertion_id] = datetime.now(timezone.utc)

        not_on_or_after = payload.get("not_on_or_after")
        if not_on_or_after:
            expiry = datetime.fromisoformat(str(not_on_or_after).replace("Z", "+00:00"))
            if expiry <= datetime.now(timezone.utc):
                raise ValueError("SAML assertion expired")

        email = (payload.get("email") or "").strip().lower()
        name_id = (payload.get("name_id") or email).strip()
        if not email:
            raise ValueError("SAML response missing email")
        if not name_id:
            raise ValueError("SAML response missing name_id")
        return {
            "email": email,
            "name_id": name_id,
            "first_name": payload.get("first_name"),
            "last_name": payload.get("last_name"),
        }

    async def verify_and_extract_saml_claims(
        self,
        db: AsyncSession,
        *,
        org_id: str,
        request_data: dict[str, Any],
    ) -> dict[str, Any]:
        config = await self._get_sso_configuration(db, org_id)
        settings_data = self._build_saml_settings(config, request_data)

        try:
            settings = OneLogin_Saml2_Settings(settings_data)
            auth = OneLogin_Saml2_Auth(request_data, old_settings=settings)
            auth.process_response()
        except Exception as exc:
            raise ValueError("Invalid SAML signature") from exc

        errors = auth.get_errors()
        if errors:
            raise ValueError(f"SAML validation failed: {','.join(errors)}")
        if not auth.is_authenticated():
            raise ValueError("SAML authentication failed")

        assertion_id_getter = getattr(auth, "get_last_assertion_id", None)
        assertion_id = assertion_id_getter() if callable(assertion_id_getter) else None
        assertion_id = (assertion_id or "").strip()
        if assertion_id:
            self._evict_stale_assertions()
            if assertion_id in self._seen_assertions:
                raise ValueError("SAML assertion replay detected")
            self._seen_assertions[assertion_id] = datetime.now(timezone.utc)

        not_on_or_after = auth.get_session_not_on_or_after()
        if not_on_or_after and int(not_on_or_after) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("SAML assertion expired")

        attributes = auth.get_attributes() or {}
        name_id = (auth.get_nameid() or "").strip()
        if not name_id:
            raise ValueError("SAML response missing name_id")

        email = self._first_attribute(
            attributes,
            "email",
            "Email",
            "mail",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        )
        if not email:
            if "@" in name_id:
                email = name_id.lower()
            else:
                raise ValueError("SAML response missing email")

        return {
            "email": email,
            "name_id": name_id,
            "first_name": self._first_attribute(
                attributes,
                "first_name",
                "givenName",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
            ),
            "last_name": self._first_attribute(
                attributes,
                "last_name",
                "surname",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
            ),
            "assertion_id": assertion_id or None,
        }

    async def provision_or_link_user(self, db: AsyncSession, user_info: dict[str, Any], org_id: Optional[str] = None) -> User:
        target_org_id = org_id or await self._resolve_org_from_email(db, user_info["email"])

        user = (await db.execute(select(User).where(User.email == user_info["email"]))).scalar_one_or_none()
        if user is None:
            username = user_info["email"].split("@", 1)[0]
            user = User(
                id=str(uuid.uuid4()),
                org_id=target_org_id,
                email=user_info["email"],
                username=username,
                hashed_password="sso_only",
                role="employee",
                is_active=True,
                must_change_password=False,
                full_name=" ".join(v for v in [user_info.get("first_name"), user_info.get("last_name")] if v) or None,
            )
            db.add(user)
            await db.flush()
        elif not user.org_id:
            user.org_id = target_org_id

        await db.execute(
            """
            INSERT INTO sso_users (id, user_id, org_id, saml_name_id, sso_only, last_saml_auth)
            VALUES (:id, :user_id, :org_id, :saml_name_id, true, :last_saml_auth)
            ON CONFLICT (saml_name_id)
            DO UPDATE SET last_saml_auth = EXCLUDED.last_saml_auth
            """,
            {
                "id": str(uuid.uuid4()),
                "user_id": user.id,
                "org_id": user.org_id,
                "saml_name_id": user_info["name_id"],
                "last_saml_auth": datetime.now(timezone.utc),
            },
        )

        return user

    def create_jwt_after_sso(self, user: User) -> str:
        if not self.jwt_secret:
            raise ValueError("JWT_SECRET_KEY is not configured")
        if not user.org_id:
            raise ValueError("User is missing org_id")

        now = datetime.now(timezone.utc)
        payload = {
            "sub": user.id,
            "email": user.email,
            "username": user.username,
            "role": user.role,
            "org_id": user.org_id,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=self.access_ttl),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    async def _resolve_org_from_email(self, db: AsyncSession, email: str) -> str:
        domain = email.split("@", 1)[1].lower()
        slug = domain.replace(".", "-")

        org = (await db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
        if org is not None:
            return org.id

        new_org = Organization(
            id=str(uuid.uuid4()),
            name=domain,
            slug=slug,
            plan="starter",
            is_active=True,
            settings={},
        )
        db.add(new_org)
        await db.flush()
        return new_org.id

    async def _get_sso_configuration(self, db: AsyncSession, org_id: str) -> dict[str, Any]:
        row = (
            await db.execute(
                """
                SELECT idp_provider, metadata_url, entity_id, acs_url, x509_cert, enabled
                FROM sso_configurations
                WHERE org_id = :org_id
                """,
                {"org_id": org_id},
            )
        ).first()
        if row is None:
            raise ValueError("SSO is not configured for this organization")
        if not bool(row[5]):
            raise ValueError("SSO is disabled for this organization")
        if not row[2] or not row[4]:
            raise ValueError("SSO provider configuration is incomplete")

        return {
            "idp_provider": row[0],
            "metadata_url": row[1],
            "entity_id": row[2],
            "acs_url": row[3],
            "x509_cert": row[4],
        }

    @staticmethod
    def build_request_data(request: Any, saml_response: str, relay_state: Optional[str] = None) -> dict[str, Any]:
        return {
            "https": "on" if request.url.scheme == "https" else "off",
            "http_host": request.url.hostname,
            "server_port": str(request.url.port or (443 if request.url.scheme == "https" else 80)),
            "script_name": request.url.path,
            "get_data": {},
            "post_data": {
                "SAMLResponse": saml_response,
                "RelayState": relay_state or "",
            },
        }

    @staticmethod
    def _build_saml_settings(config: dict[str, Any], request_data: dict[str, Any]) -> dict[str, Any]:
        scheme = "https" if request_data.get("https") == "on" else "http"
        host = request_data.get("http_host")
        port = request_data.get("server_port")
        script_name = request_data.get("script_name", "/auth/sso/acs")
        acs_url = config.get("acs_url") or f"{scheme}://{host}:{port}{script_name}"

        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": os.getenv("SAML_SP_ENTITY_ID", "https://resilo.local/auth/sso/metadata"),
                "assertionConsumerService": {
                    "url": acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            },
            "idp": {
                "entityId": config["entity_id"],
                "singleSignOnService": {
                    "url": config.get("metadata_url") or "https://example.okta.com/app/sso/saml",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": config["x509_cert"],
            },
            "security": {
                "wantAssertionsSigned": True,
                "wantMessagesSigned": True,
                "wantNameId": True,
                "wantNameIdEncrypted": False,
                "requestedAuthnContext": True,
                "wantAttributeStatement": True,
                "rejectDeprecatedAlgorithm": True,
            },
        }

    @staticmethod
    def _first_attribute(attributes: dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            values = attributes.get(key)
            if not values:
                continue
            if isinstance(values, list):
                value = str(values[0]).strip() if values else ""
            else:
                value = str(values).strip()
            if value:
                return value
        return None

    @classmethod
    def _evict_stale_assertions(cls) -> None:
        now = datetime.now(timezone.utc)
        stale_keys = [k for k, v in cls._seen_assertions.items() if (now - v).total_seconds() > 300]
        for key in stale_keys:
            cls._seen_assertions.pop(key, None)
