"""
auth_api.py — AIOps Bot Authentication & User Management Service

FastAPI application running on port 5001.

Start:
    uvicorn auth_api:app --host 0.0.0.0 --port 5001 --reload

Required environment variables (set in .env):
    DATABASE_URL       postgresql+asyncpg://aiops:aiops@localhost:5432/aiops
    JWT_SECRET_KEY     a long random string — NEVER change in production
    FRONTEND_URL       http://localhost:3001  (used in invite / reset links)

Optional:
    JWT_ACCESS_TTL     seconds (default 86400 = 24 h)
    JWT_REFRESH_TTL    seconds (default 2592000 = 30 d)
    EMAIL_SMTP_SERVER  SMTP host
    SMTP_PORT          (default 587)
    EMAIL_USERNAME     SMTP user
    EMAIL_PASSWORD     SMTP password
    EMAIL_FROM         from address
"""

import os
import hashlib
import hmac as _hmac
import secrets
import struct
import time
import base64
import logging
import smtplib
import uuid
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List

import bcrypt
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    init_db, get_db, SessionLocal,
    User, UserSession, InviteToken, PasswordResetToken, Organization,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("auth_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# JWT config — secret MUST come from env in production
# ---------------------------------------------------------------------------
_jwt_secret = os.getenv("JWT_SECRET_KEY", "")
if not _jwt_secret:
    _jwt_secret = secrets.token_urlsafe(48)
    log.warning(
        "JWT_SECRET_KEY not set — using ephemeral secret. "
        "All sessions will be lost on restart. Add JWT_SECRET_KEY to .env"
    )

JWT_SECRET      = _jwt_secret
JWT_ALGORITHM   = "HS256"
JWT_ACCESS_TTL  = int(os.getenv("JWT_ACCESS_TTL", "86400"))      # 24 h
JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL", "2592000"))   # 30 d
FRONTEND_URL    = os.getenv("FRONTEND_URL", "http://localhost:3001")

VALID_ROLES = {"admin", "manager", "employee", "guest"}

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="AIOps Auth API", version="2.0.0", docs_url="/auth/docs")

# Wildcard origins with allow_credentials=True is a critical misconfiguration —
# it allows any site on the internet to make authenticated requests on behalf
# of your logged-in users (session riding / credential theft).
# ALLOWED_ORIGINS must be a comma-separated list of your actual frontend URLs.
_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        f"{FRONTEND_URL},http://localhost:3000,http://127.0.0.1:3001,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Startup — create tables + seed default admin
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup():
    await init_db()
    await _seed_admin()


async def _seed_admin():
    async with SessionLocal() as db:
        # Create default org if none exists
        org_count = await db.execute(select(sqlfunc.count()).select_from(Organization))
        if org_count.scalar() == 0:
            org = Organization(
                id=str(uuid.uuid4()),
                name="Default Organization",
                slug="default",
                plan="enterprise",
                settings={"autonomous_mode": False},
            )
            db.add(org)
            await db.flush()
            org_id = org.id
            log.info("Default organization created (id=%s)", org_id)
        else:
            org_result = await db.execute(select(Organization).limit(1))
            org = org_result.scalar_one()
            org_id = org.id

        # Create default admin if no users exist
        user_count = await db.execute(select(sqlfunc.count()).select_from(User))
        if user_count.scalar() == 0:
            # Never hardcode a default password — read from env so it never
            # appears in source code or (worse) in structured logs shipped to
            # an aggregator. If unset, generate a random one and surface it
            # via reset_admin_password.py instead.
            _default_pw = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
            if not _default_pw:
                _default_pw = secrets.token_urlsafe(20)
                log.warning(
                    "ADMIN_DEFAULT_PASSWORD not set. A random password was used "
                    "for admin@company.local. Run reset_admin_password.py to set "
                    "a known password before first login."
                )
            pw_hash = _hash_password(_default_pw)
            admin = User(
                id=str(uuid.uuid4()),
                email="admin@company.local",
                username="admin",
                hashed_password=pw_hash,
                role="admin",
                org_id=org_id,
                full_name="Default Admin",
                must_change_password=True,
            )
            db.add(admin)
            await db.commit()
            log.warning(
                "Default admin account created (admin@company.local). "
                "LOGIN AND CHANGE THE PASSWORD IMMEDIATELY."
            )
        else:
            # Assign existing users without an org_id to the default org
            await db.execute(
                __import__("sqlalchemy").text(
                    f"UPDATE users SET org_id = '{org_id}' WHERE org_id IS NULL"
                )
            )
            await db.commit()


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------
def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# TOTP (RFC 6238) — stdlib only, no pyotp needed
# ---------------------------------------------------------------------------
def _totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def _totp_code(secret: str, at: int = None) -> str:
    key = base64.b32decode(secret.upper().replace(" ", ""))
    t = (((at or int(time.time())) // 30)).to_bytes(8, "big")
    h = _hmac.new(key, t, "sha1").digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset: offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def _totp_verify(secret: str, code: str, window: int = 1) -> bool:
    now = int(time.time())
    for delta in range(-window, window + 1):
        if _hmac.compare_digest(_totp_code(secret, now + delta * 30), code.strip()):
            return True
    return False


def _totp_uri(secret: str, email: str) -> str:
    from urllib.parse import quote
    return (
        f"otpauth://totp/AIOps%20Bot:{quote(email)}"
        f"?secret={secret}&issuer=AIOps%20Bot&algorithm=SHA1&digits=6&period=30"
    )


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def _make_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "username": user.username,
        "org_id": user.org_id,       # multi-tenancy: org scope in every token
        "iat": now,
        "exp": now + timedelta(seconds=JWT_ACCESS_TTL),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _make_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash)."""
    raw = secrets.token_urlsafe(48)
    h = hashlib.sha256(raw.encode()).hexdigest()
    return raw, h


def _decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# Auth dependency — get current user from Bearer token
# ---------------------------------------------------------------------------
async def _current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not creds:
        raise exc
    try:
        payload = _decode_access_token(creds.credentials)
        if payload.get("type") != "access":
            raise exc
        user_id: str = payload["sub"]
    except (JWTError, KeyError):
        raise exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise exc
    return user


def _require_admin(user: User = Depends(_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Email helper
# ---------------------------------------------------------------------------
def _send_email(to: str, subject: str, html: str, plain: str = "") -> bool:
    host = os.getenv("EMAIL_SMTP_SERVER", os.getenv("SMTP_SERVER", ""))
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("EMAIL_USERNAME", "")
    pw   = os.getenv("EMAIL_PASSWORD", "")
    frm  = os.getenv("EMAIL_FROM", user)
    if not (host and user and pw):
        log.info("SMTP not configured — would have sent to %s: %s", to, subject)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = frm
        msg["To"] = to
        msg.attach(MIMEText(plain or html, "plain"))
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            s.starttls()
            s.login(user, pw)
            s.sendmail(frm, [to], msg.as_string())
        return True
    except Exception as e:
        log.error("Email send failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


class TwoFAVerifyRequest(BaseModel):
    temp_token: str
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class Enable2FARequest(BaseModel):
    code: str


class Disable2FARequest(BaseModel):
    code: str


class CreateUserRequest(BaseModel):
    email: str
    username: str
    password: str
    role: str = "employee"
    full_name: Optional[str] = None
    must_change_password: bool = True


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str
    must_change_password: bool = True


class CreateInviteRequest(BaseModel):
    role: str = "employee"
    email: Optional[str] = None
    note: Optional[str] = None
    ttl_hours: int = 72


class AcceptInviteRequest(BaseModel):
    token: str
    email: str
    username: str
    password: str
    full_name: Optional[str] = None

class RegisterOrgRequest(BaseModel):
    org_name: str
    email: str
    username: str
    password: str
    full_name: Optional[str] = None


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "role": u.role,
        "org_id": u.org_id,
        "full_name": u.full_name,
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "two_factor_enabled": u.two_factor_enabled,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


# ---------------------------------------------------------------------------
# In-memory 2FA pending tokens (5-minute TTL)
# ---------------------------------------------------------------------------
_pending_2fa: dict = {}


def _create_2fa_pending(user_id: str) -> str:
    tok = secrets.token_urlsafe(24)
    _pending_2fa[tok] = {"user_id": user_id, "exp": time.time() + 300}
    return tok


def _consume_2fa_pending(temp: str) -> Optional[str]:
    entry = _pending_2fa.pop(temp, None)
    if not entry or time.time() > entry["exp"]:
        return None
    return entry["user_id"]


# ---------------------------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------------------------

@app.post("/auth/login")
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not _verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # 2FA gate
    if user.two_factor_enabled and user.two_factor_secret:
        temp = _create_2fa_pending(user.id)
        return {"requires_2fa": True, "temp_token": temp}

    # Issue tokens
    access = _make_access_token(user)
    raw_refresh, refresh_hash = _make_refresh_token()

    session = UserSession(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=JWT_REFRESH_TTL),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    resp: dict = {
        "token": access,
        "refresh_token": raw_refresh,
        "user": _user_out(user),
    }
    if user.must_change_password:
        resp["must_change_password"] = True
    return resp


@app.post("/auth/2fa/verify")
async def verify_2fa(body: TwoFAVerifyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = _consume_2fa_pending(body.temp_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA session")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    if not _totp_verify(user.two_factor_secret, body.code):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    access = _make_access_token(user)
    raw_refresh, refresh_hash = _make_refresh_token()

    session = UserSession(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=JWT_REFRESH_TTL),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    return {"token": access, "refresh_token": raw_refresh, "user": _user_out(user)}


@app.post("/auth/refresh")
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(UserSession).where(
            UserSession.refresh_token_hash == token_hash,
            UserSession.is_revoked == False,
            UserSession.expires_at > now,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    result2 = await db.execute(select(User).where(User.id == session.user_id))
    user = result2.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate refresh token
    session.is_revoked = True
    new_access = _make_access_token(user)
    raw_refresh, refresh_hash = _make_refresh_token()

    new_session = UserSession(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        expires_at=now + timedelta(seconds=JWT_REFRESH_TTL),
        ip_address=session.ip_address,
        user_agent=session.user_agent,
    )
    db.add(new_session)
    await db.commit()

    return {"token": new_access, "refresh_token": raw_refresh}


@app.post("/auth/logout")
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(UserSession).where(UserSession.refresh_token_hash == token_hash)
    )
    session = result.scalar_one_or_none()
    if session:
        session.is_revoked = True
        await db.commit()
    return {"ok": True}


@app.get("/auth/me")
async def me(user: User = Depends(_current_user)):
    return _user_out(user)


@app.post("/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(_current_user),
    db: AsyncSession = Depends(get_db),
):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user.hashed_password = _hash_password(body.new_password)
    user.must_change_password = False
    await db.commit()
    return {"ok": True}


@app.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Always return 200 to avoid email enumeration
    if user and user.is_active:
        raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(prt)
        await db.commit()
        reset_url = f"{FRONTEND_URL}/reset-password?token={raw}"
        sent = _send_email(
            user.email,
            "AIOps Bot — Password Reset",
            f"<p>Click to reset your password (valid 1 hour):</p><p><a href='{reset_url}'>{reset_url}</a></p>",
            plain=f"Password reset link (valid 1 hour): {reset_url}",
        )
        if not sent:
            log.info("Password reset URL for %s: %s", user.email, reset_url)
    return {"ok": True, "message": "If that email exists, a reset link has been sent"}


@app.post("/auth/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        )
    )
    prt = result.scalar_one_or_none()
    if not prt:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    result2 = await db.execute(select(User).where(User.id == prt.user_id))
    user = result2.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = _hash_password(body.new_password)
    user.must_change_password = False
    prt.used = True
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 2FA ROUTES
# ---------------------------------------------------------------------------

@app.get("/auth/2fa/status")
async def twofa_status(user: User = Depends(_current_user)):
    return {"enabled": user.two_factor_enabled}


@app.post("/auth/2fa/setup")
async def twofa_setup(user: User = Depends(_current_user), db: AsyncSession = Depends(get_db)):
    secret = _totp_secret()
    user.two_factor_secret = secret
    await db.commit()
    return {
        "secret": secret,
        "uri": _totp_uri(secret, user.email),
    }


@app.post("/auth/2fa/enable")
async def twofa_enable(body: Enable2FARequest, user: User = Depends(_current_user), db: AsyncSession = Depends(get_db)):
    if not user.two_factor_secret:
        raise HTTPException(status_code=400, detail="Call /auth/2fa/setup first")
    if not _totp_verify(user.two_factor_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    user.two_factor_enabled = True
    await db.commit()
    return {"ok": True}


@app.post("/auth/2fa/disable")
async def twofa_disable(body: Disable2FARequest, user: User = Depends(_current_user), db: AsyncSession = Depends(get_db)):
    if not user.two_factor_enabled or not user.two_factor_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")
    if not _totp_verify(user.two_factor_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    user.two_factor_enabled = False
    user.two_factor_secret = None
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# USER MANAGEMENT (admin only)
# ---------------------------------------------------------------------------

@app.get("/users")
async def list_users(admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    # Scope to the admin's own org — admins cannot see users from other orgs
    q = select(User).order_by(User.created_at.desc())
    if admin.org_id:
        q = q.where(User.org_id == admin.org_id)
    result = await db.execute(q)
    users = result.scalars().all()
    return [_user_out(u) for u in users]


@app.post("/users", status_code=201)
async def create_user(body: CreateUserRequest, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Check uniqueness
    dup_email = await db.execute(select(User).where(User.email == body.email))
    if dup_email.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")
    dup_user = await db.execute(select(User).where(User.username == body.username))
    if dup_user.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already in use")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=_hash_password(body.password),
        role=body.role,
        full_name=body.full_name,
        must_change_password=body.must_change_password,
        org_id=admin.org_id,  # inherit org from the creating admin
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(user)


@app.get("/users/{user_id}")
async def get_user(user_id: str, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(user)


@app.put("/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role")
        # Prevent removing the last admin
        if user.role == "admin" and body.role != "admin":
            count_result = await db.execute(
                select(sqlfunc.count()).select_from(User).where(User.role == "admin", User.is_active == True)
            )
            if count_result.scalar() <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the last active admin")
        user.role = body.role

    if body.is_active is not None:
        user.is_active = body.is_active

    if body.full_name is not None:
        user.full_name = body.full_name

    await db.commit()
    await db.refresh(user)
    return _user_out(user)


@app.delete("/users/{user_id}")
async def deactivate_user(user_id: str, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    # Prevent deactivating the last admin
    if user.role == "admin":
        count_result = await db.execute(
            select(sqlfunc.count()).select_from(User).where(User.role == "admin", User.is_active == True)
        )
        if count_result.scalar() <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")

    user.is_active = False
    # Revoke all sessions
    sessions_result = await db.execute(select(UserSession).where(UserSession.user_id == user_id))
    for s in sessions_result.scalars().all():
        s.is_revoked = True

    await db.commit()
    return {"ok": True}


@app.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    body: AdminResetPasswordRequest,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user.hashed_password = _hash_password(body.new_password)
    user.must_change_password = body.must_change_password
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# INVITE SYSTEM (admin only)
# ---------------------------------------------------------------------------

@app.get("/auth/invites")
async def list_invites(admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(select(InviteToken).order_by(InviteToken.created_at.desc()))
    invites = result.scalars().all()
    out = []
    for inv in invites:
        out.append({
            "id": inv.id,
            "token": inv.token,
            "email": inv.email,
            "role": inv.role,
            "note": inv.note,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            "used_at": inv.used_at.isoformat() if inv.used_at else None,
            "status": "used" if inv.used_at else ("expired" if inv.expires_at < now else "pending"),
            "accept_url": f"{FRONTEND_URL}/accept-invite?token={inv.token}",
        })
    return out


@app.post("/auth/invites", status_code=201)
async def create_invite(
    body: CreateInviteRequest,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role")

    raw_token = secrets.token_urlsafe(32)
    invite = InviteToken(
        token=raw_token,
        email=body.email,
        role=body.role,
        note=body.note,
        created_by=admin.id,
        org_id=admin.org_id,   # scope invite to admin's org
        expires_at=datetime.now(timezone.utc) + timedelta(hours=body.ttl_hours),
    )
    db.add(invite)
    await db.commit()

    accept_url = f"{FRONTEND_URL}/accept-invite?token={raw_token}"
    # Send email if address specified
    if body.email:
        sent = _send_email(
            body.email,
            "You've been invited to AIOps Bot",
            f"<p>You have been invited as <b>{body.role}</b>. "
            f"<a href='{accept_url}'>Click here to set up your account</a> (expires in {body.ttl_hours}h).</p>",
            plain=f"You have been invited as {body.role}. Set up your account: {accept_url}",
        )
        if not sent:
            log.info("Invite URL for %s: %s", body.email, accept_url)

    return {
        "token": raw_token,
        "accept_url": accept_url,
        "role": body.role,
        "email": body.email,
        "expires_in_hours": body.ttl_hours,
    }


@app.delete("/auth/invites/{token}")
async def revoke_invite(token: str, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InviteToken).where(InviteToken.token == token))
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    await db.delete(invite)
    await db.commit()
    return {"ok": True}


@app.post("/auth/accept-invite", status_code=201)
async def accept_invite(body: AcceptInviteRequest, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(InviteToken).where(
            InviteToken.token == body.token,
            InviteToken.used_at == None,
            InviteToken.expires_at > now,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid or expired invite token")

    # Validate email matches if invite was for specific email
    if invite.email and invite.email.lower() != body.email.lower():
        raise HTTPException(status_code=400, detail="This invite was issued for a different email address")

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Check uniqueness
    dup = await db.execute(select(User).where(User.email == body.email))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    dup2 = await db.execute(select(User).where(User.username == body.username))
    if dup2.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already in use")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=_hash_password(body.password),
        role=invite.role,
        org_id=invite.org_id,   # inherit org from invite
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()

    invite.used_at = now
    invite.used_by = user.id
    await db.commit()
    return {"ok": True, "message": "Account created. You can now log in."}


# ---------------------------------------------------------------------------
# Self-service admin registration — creates a new org + admin user
# ---------------------------------------------------------------------------
@app.post("/auth/register", status_code=201)
async def register_org(body: RegisterOrgRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a brand-new organization and its first admin user in one step.
    Anyone can call this — it's the entry point for new accounts.
    """
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    org_name = body.org_name.strip()
    if not org_name:
        raise HTTPException(status_code=400, detail="Organization name is required")

    # Derive a URL-safe slug from the org name
    import re
    slug_base = re.sub(r'[^a-z0-9]+', '-', org_name.lower()).strip('-') or "org"
    # Ensure slug uniqueness
    slug = slug_base
    counter = 1
    while True:
        exists = await db.execute(select(Organization).where(Organization.slug == slug))
        if not exists.scalar_one_or_none():
            break
        slug = f"{slug_base}-{counter}"
        counter += 1

    # Check user uniqueness before creating the org
    dup_email = await db.execute(select(User).where(User.email == body.email))
    if dup_email.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    dup_user = await db.execute(select(User).where(User.username == body.username))
    if dup_user.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already in use")

    # Create the organization
    org = Organization(name=org_name, slug=slug, plan="free")
    db.add(org)
    await db.flush()  # get org.id

    # Create the admin user
    user = User(
        email=body.email,
        username=body.username,
        hashed_password=_hash_password(body.password),
        role="admin",
        org_id=org.id,
        full_name=body.full_name,
        must_change_password=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    log.info("New org registered: %s (id=%s) by %s", org_name, org.id, body.email)
    return {"ok": True, "message": "Organization created. You can now sign in.", "org_id": org.id}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/auth/health")
async def health():
    return {"status": "ok", "service": "auth-api", "version": "2.0.0"}
