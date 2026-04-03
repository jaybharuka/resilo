"""
auth_api.py Ã¢â‚¬â€ AIOps Bot Authentication & User Management Service

FastAPI application running on port 5001.

Start:
    uvicorn auth_api:app --host 0.0.0.0 --port 5001 --reload

Required environment variables (set in .env):
    DATABASE_URL       postgresql+asyncpg://aiops:aiops@localhost:5432/aiops
    JWT_SECRET_KEY     a long random string Ã¢â‚¬â€ NEVER change in production
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

# Load .env from repo root so JWT_SECRET_KEY etc. are available
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_file = os.path.join(_root, '.env')
if os.path.exists(_env_file):
    with open(_env_file) as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

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
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.database import (
    init_db, get_db, SessionLocal,
    User, UserSession, InviteToken, PasswordResetToken, Organization, APIKey,
)
from app.core.logging_config import get_logger, set_correlation_id, get_correlation_id
from app.core.metrics import metrics_middleware, get_metrics
from app.core.trace_context import init_trace_context, get_propagation_headers
from app.core.audit import audit_log
from app.auth.authz import require_org_access, require_admin_in_org
from apikey import generate_api_key, hash_api_key, validate_api_key
from config import validate_secrets
from retention import cleanup_all_expired_data
from backup import create_backup_async, cleanup_old_backups, get_recent_backups, verify_backup

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = get_logger("auth_api")

# ---------------------------------------------------------------------------
# JWT config Ã¢â‚¬â€ secret MUST come from env in production
# ---------------------------------------------------------------------------
_jwt_secret = os.getenv("JWT_SECRET_KEY")
if not _jwt_secret:
    raise RuntimeError("JWT_SECRET_KEY env var is required but not set")
JWT_SECRET      = _jwt_secret
JWT_ALGORITHM   = "HS256"
JWT_ACCESS_TTL  = int(os.getenv("JWT_ACCESS_TTL", "86400"))      # 24 h
JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL", "2592000"))   # 30 d
FRONTEND_URL    = os.getenv("FRONTEND_URL", "http://localhost:3001")

VALID_ROLES = {"admin", "manager", "employee", "guest"}

# ---------------------------------------------------------------------------
# Sentry initialization for error tracking
# ---------------------------------------------------------------------------
_SENTRY_DSN = os.getenv('SENTRY_DSN')
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment=os.getenv('ENVIRONMENT', 'development')
    )

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="AIOps Auth API", version="2.0.0", docs_url="/auth/docs")

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: HTTPException(status_code=429, detail="Too many requests"))

# Correlation ID middleware for request tracing
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """
    Initialize trace context (W3C Trace Context + X-Request-ID) for request tracing.
    Enables correlation of logs across distributed services.
    """
    # Initialize trace context from incoming headers
    traceparent = request.headers.get("traceparent")
    request_id = request.headers.get("X-Request-ID")
    init_trace_context(traceparent=traceparent, request_id=request_id)
    
    # Set correlation ID for logging
    set_correlation_id(request_id or str(uuid.uuid4()))
    
    response = await call_next(request)
    
    # Propagate trace context in response headers
    propagation_headers = get_propagation_headers()
    for header_name, header_value in propagation_headers.items():
        response.headers[header_name] = header_value
    
    return response


# Request/response logging middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log all requests and responses with structured context."""
    import time
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    log.info(
        "HTTP request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "client_ip": request.client.host if request.client else "unknown",
        }
    )
    return response


# Metrics middleware (must be before other middleware to measure all requests)
@app.middleware("http")
async def metrics_middleware_wrapper(request: Request, call_next):
    """Collect request metrics for Prometheus."""
    return await metrics_middleware(request, call_next)


# HTTPS redirect and security headers middleware
@app.middleware("http")
async def https_and_security_middleware(request: Request, call_next):
    """Enforce HTTPS and add security headers."""
    # Redirect HTTP to HTTPS in production (check X-Forwarded-Proto for reverse proxy)
    proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    if proto == "http" and os.getenv("ENVIRONMENT", "development") == "production":
        return HTTPException(status_code=403, detail="HTTPS required")
    
    response = await call_next(request)
    
    # Add security headers
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' http: https:; frame-ancestors 'none'"
    
    return response

# Wildcard origins with allow_credentials=True is a critical misconfiguration Ã¢â‚¬â€
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
# Global exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions, log them, and return safe error response."""
    log.error(
        "Unhandled exception",
        extra={
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "path": request.url.path,
            "method": request.method,
        },
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_id": get_correlation_id()},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError with 400 Bad Request."""
    log.warning(
        "Value error",
        extra={
            "exception_message": str(exc),
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=400,
        content={"detail": "Invalid value provided", "error_id": get_correlation_id()},
    )


@app.exception_handler(TypeError)
async def type_error_handler(request: Request, exc: TypeError):
    """Handle TypeError with 400 Bad Request."""
    log.warning(
        "Type error",
        extra={
            "exception_message": str(exc),
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=400,
        content={"detail": "Invalid request format", "error_id": get_correlation_id()},
    )


# ---------------------------------------------------------------------------
# Startup Ã¢â‚¬â€ validate secrets + create tables + seed default admin
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup():
    # Validate all required secrets are present before doing anything else
    validate_secrets()
    
    # Create tables (simplified - skip Alembic migrations for demo)
    try:
        from app.core.database import Base, engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Database tables created successfully")
    except Exception as e:
        log.error(f"Failed to create tables: {e}")
    
    await _seed_admin()
    
    # Note: Data retention cleanup and backups can be run separately via scheduled tasks
    # Commenting out on startup to allow faster server initialization
    # async with SessionLocal() as db:
    #     await cleanup_all_expired_data(db)


async def _seed_admin():
    """
    Ensure the default admin account exists and its password always matches
    ADMIN_DEFAULT_PASSWORD from .env.  Running this on every startup means
    the password is never silently randomised Ã¢â‚¬â€ what is in .env is the truth.
    """
    _dev_pw = os.getenv("ADMIN_DEFAULT_PASSWORD", "Admin@1234")

    async with SessionLocal() as db:
        # Ã¢â€â‚¬Ã¢â€â‚¬ Ensure default org exists Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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

        # Ã¢â€â‚¬Ã¢â€â‚¬ Upsert admin@company.local Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        result = await db.execute(
            select(User).where((User.email == "admin@company.local") | (User.username == "admin"))
        )
        admin = result.scalar_one_or_none()
        pw_hash = _hash_password(_dev_pw)

        if admin is None:
            admin = User(
                id=str(uuid.uuid4()),
                email="admin@company.local",
                username="admin",
                hashed_password=pw_hash,
                role="admin",
                org_id=org_id,
                full_name="Default Admin",
                must_change_password=False,
            )
            db.add(admin)
            log.info("Default admin account created (admin@company.local)")
        else:
            # Always re-sync the password so a stale/random hash never blocks login
            admin.hashed_password    = pw_hash
            admin.must_change_password = False
            admin.is_active          = True
            if not admin.org_id:
                admin.org_id = org_id
            log.info("Admin account synced (admin@company.local)")

        # Migrate any other users that slipped through without an org
        await db.execute(
            __import__("sqlalchemy").text(
                f"UPDATE users SET org_id = '{org_id}' WHERE org_id IS NULL"
            )
        )
        await db.commit()
        log.info(
            "Admin ready Ã¢â‚¬â€ email: admin@company.local  "
            "password: (from ADMIN_DEFAULT_PASSWORD in .env)"
        )


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


def _validate_password(pw: str) -> None:
    import re
    errors = []
    if len(pw) < 12:
        errors.append("at least 12 characters")
    if not re.search(r"[A-Z]", pw):
        errors.append("an uppercase letter")
    if not re.search(r"[a-z]", pw):
        errors.append("a lowercase letter")
    if not re.search(r"\d", pw):
        errors.append("a digit")
    if not re.search(r"[^A-Za-z0-9]", pw):
        errors.append("a special character")
    if errors:
        raise HTTPException(
            status_code=400,
            detail=f"Password must contain {', '.join(errors)}",
        )


# ---------------------------------------------------------------------------
# TOTP (RFC 6238) Ã¢â‚¬â€ stdlib only, no pyotp needed
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
# Auth dependency Ã¢â‚¬â€ get current user from Bearer token
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
        log.info("SMTP not configured Ã¢â‚¬â€ would have sent to %s: %s", to, subject)
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
from pydantic import Field, field_validator
import re

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class TwoFAVerifyRequest(BaseModel):
    temp_token: str = Field(..., min_length=1, max_length=256)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=512)


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=1, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)
    new_password: str = Field(..., min_length=1, max_length=256)


class Enable2FARequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class Disable2FARequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class CreateUserRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(..., min_length=1, max_length=256)
    role: str = Field(default="employee", min_length=1, max_length=20)
    full_name: Optional[str] = Field(None, max_length=255)
    must_change_password: bool = True


class UpdateUserRequest(BaseModel):
    role: Optional[str] = Field(None, min_length=1, max_length=20)
    is_active: Optional[bool] = None
    full_name: Optional[str] = Field(None, max_length=255)


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=1, max_length=256)
    must_change_password: bool = True


class CreateInviteRequest(BaseModel):
    role: str = Field(default="employee", min_length=1, max_length=20)
    email: Optional[EmailStr] = None
    note: Optional[str] = Field(None, max_length=1000)
    ttl_hours: int = Field(default=72, ge=1, le=720)


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(..., min_length=1, max_length=256)
    full_name: Optional[str] = Field(None, max_length=255)


class RegisterOrgRequest(BaseModel):
    org_name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9\s\-._]+$")
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(..., min_length=1, max_length=256)
    full_name: Optional[str] = Field(None, max_length=255)


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

@app.post("/auth/login", tags=["Authentication"])
@limiter.limit("5/minute")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user with email and password.
    
    Returns access token and refresh token on success.
    If 2FA is enabled, returns temp_token instead and requires /auth/verify-2fa.
    
    **Rate limit**: 5 requests per minute per IP
    
    **Responses**:
    - 200: Login successful, returns access_token, refresh_token, user
    - 200: 2FA required, returns requires_2fa=true, temp_token
    - 401: Invalid email or password
    - 403: Account disabled
    - 429: Rate limit exceeded
    """
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


@app.post("/auth/change-password", tags=["Authentication"])
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the current user's password.
    
    Updates the authenticated user's password. Password must meet complexity requirements.
    Clears the must_change_password flag if set.
    
    **Authentication**: Requires valid JWT access token
    
    **Responses**:
    - 200: Password changed successfully
    - 400: Invalid password format
    - 401: Missing or invalid authentication token
    - 500: Database error during update
    """
    _validate_password(body.new_password)
    user.hashed_password = _hash_password(body.new_password)
    user.must_change_password = False
    await db.commit()
    
    # Audit log password change
    await audit_log(
        db,
        action="password_changed",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        org_id=user.org_id,
        detail={"email": user.email},
        request=None,
    )
    await db.commit()
    
    return {"ok": True}


@app.post("/auth/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
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
            "AIOps Bot Ã¢â‚¬â€ Password Reset",
            f"<p>Click to reset your password (valid 1 hour):</p><p><a href='{reset_url}'>{reset_url}</a></p>",
            plain=f"Password reset link (valid 1 hour): {reset_url}",
        )
        if not sent:
            log.info("Password reset URL for %s: %s", user.email, reset_url)
    return {"ok": True, "message": "If that email exists, a reset link has been sent"}


@app.post("/auth/reset-password")
@limiter.limit("3/hour")
async def reset_password(body: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
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

    _validate_password(body.new_password)

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
    # Scope to the admin's own org Ã¢â‚¬â€ admins cannot see users from other orgs
    q = select(User).order_by(User.created_at.desc())
    if admin.org_id:
        q = q.where(User.org_id == admin.org_id)
    result = await db.execute(q)
    users = result.scalars().all()
    return [_user_out(u) for u in users]


@app.post("/users", status_code=201, tags=["User Management"])
async def create_user(body: CreateUserRequest, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    """
    Create a new user in the organization (admin only).
    
    Creates a user with the specified email, username, password, and role.
    Password must meet complexity requirements. User is created in the same org as the admin.
    
    **Authentication**: Requires valid JWT access token with admin role
    
    **Responses**:
    - 201: User created successfully
    - 400: Invalid role, email format, username format, or password
    - 401: Missing or invalid authentication token
    - 403: User lacks admin permission
    - 409: Email or username already in use
    - 500: Database error during creation
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    _validate_password(body.password)

    try:
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
        
        # Audit log user creation
        await audit_log(
            db,
            action="user_created",
            resource_type="user",
            resource_id=user.id,
            user_id=admin.id,
            org_id=admin.org_id,
            detail={"email": user.email, "username": user.username, "role": user.role},
            request=None,
        )
        await db.commit()
        
        return _user_out(user)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        log.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")


@app.get("/users/{user_id}")
async def get_user(user_id: str, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Verify admin has access to this user's org
    await require_org_access(admin, user.org_id)
    return _user_out(user)


@app.put("/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest, admin: User = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Verify admin has access to this user's org
    await require_org_access(admin, user.org_id)

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
    # Verify admin has access to this user's org
    await require_org_access(admin, user.org_id)
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
    _validate_password(body.new_password)

    try:
        user.hashed_password = _hash_password(body.new_password)
        user.must_change_password = body.must_change_password
        await db.commit()
        return {"ok": True}
    except Exception as e:
        await db.rollback()
        log.error(f"Error resetting password: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset password")


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

    # Invites are always created for the admin's own org
    org_id = admin.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Admin must belong to an organization")

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


# ---------------------------------------------------------------------------
# API Key Management (service-to-service authentication)
# ---------------------------------------------------------------------------

class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name for the API key (e.g., 'core_api', 'notification_service')")


@app.post("/auth/api-keys", status_code=201, tags=["API Keys"])
async def create_api_key(
    body: CreateAPIKeyRequest,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new API key for service-to-service authentication.
    
    Returns the raw API key only once. Store it securely and use in X-API-Key header.
    
    **Authentication**: Requires valid JWT access token with admin role
    
    **Responses**:
    - 201: API key created successfully
    - 400: Invalid name
    - 401: Missing or invalid authentication token
    - 403: User lacks admin permission
    """
    if not admin.org_id:
        raise HTTPException(status_code=400, detail="Admin must belong to an organization")
    
    # Generate raw key and hash
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    
    api_key = APIKey(
        org_id=admin.org_id,
        name=body.name,
        key_hash=key_hash,
        created_by=admin.id,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    # Audit log API key creation
    await audit_log(
        db,
        action="api_key_created",
        resource_type="api_key",
        resource_id=api_key.id,
        user_id=admin.id,
        org_id=admin.org_id,
        detail={"name": api_key.name},
        request=None,
    )
    await db.commit()
    
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,  # Only shown once
        "message": "Store this key securely. You won't be able to see it again.",
    }


@app.get("/auth/api-keys", tags=["API Keys"])
async def list_api_keys(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    List all API keys for the organization (admin only).
    
    Does not return the raw key values (only hashes).
    """
    if not admin.org_id:
        raise HTTPException(status_code=400, detail="Admin must belong to an organization")
    
    result = await db.execute(
        select(APIKey).where(APIKey.org_id == admin.org_id).order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    
    return [
        {
            "id": k.id,
            "name": k.name,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        }
        for k in keys
    ]


@app.delete("/auth/api-keys/{key_id}", tags=["API Keys"])
async def revoke_api_key(
    key_id: str,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke an API key (admin only).
    
    Revoked keys cannot be used for authentication.
    """
    if not admin.org_id:
        raise HTTPException(status_code=400, detail="Admin must belong to an organization")
    
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.org_id == admin.org_id)
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    
    api_key.revoked_at = datetime.now(timezone.utc)
    api_key.is_active = False
    await db.commit()
    
    # Audit log API key revocation
    await audit_log(
        db,
        action="api_key_revoked",
        resource_type="api_key",
        resource_id=api_key.id,
        user_id=admin.id,
        org_id=admin.org_id,
        detail={"name": api_key.name},
        request=None,
    )
    await db.commit()
    
    return {"ok": True}


@app.post("/auth/accept-invite", status_code=201)
@limiter.limit("3/hour")
async def accept_invite(body: AcceptInviteRequest, request: Request, db: AsyncSession = Depends(get_db)):
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

    _validate_password(body.password)

    try:
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
        
        # Audit log invite acceptance
        await audit_log(
            db,
            action="invite_accepted",
            resource_type="invite",
            resource_id=invite.id,
            user_id=user.id,
            org_id=invite.org_id,
            detail={"email": user.email, "role": user.role},
            request=request,
        )
        await db.commit()
        
        return {"ok": True, "message": "Account created. You can now log in."}
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        log.error(f"Error accepting invite: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept invite")


# ---------------------------------------------------------------------------
# Self-service admin registration Ã¢â‚¬â€ creates a new org + admin user
# ---------------------------------------------------------------------------
@app.post("/auth/register", status_code=201, tags=["Authentication"])
@limiter.limit("3/hour")
async def register_org(body: RegisterOrgRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create a brand-new organization and its first admin user in one step.
    
    This is the entry point for new accounts. Creates org with auto-generated slug,
    creates admin user with provided credentials. Password must meet complexity requirements.
    
    **Rate limit**: 3 requests per hour per IP
    
    **Responses**:
    - 201: Organization created successfully
    - 400: Invalid org name, email, or password
    - 409: Email or username already in use
    - 429: Rate limit exceeded
    - 500: Database error during creation
    """
    _validate_password(body.password)

    org_name = body.org_name.strip()
    if not org_name:
        raise HTTPException(status_code=400, detail="Organization name is required")

    try:
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

        # Audit log organization creation
        await audit_log(
            db,
            action="organization_created",
            resource_type="organization",
            resource_id=org.id,
            user_id=user.id,
            org_id=org.id,
            detail={"org_name": org.name, "slug": org.slug, "plan": org.plan},
            request=request,
        )
        await db.commit()

        log.info("New org registered: %s (id=%s) by %s", org_name, org.id, body.email)
        return {"ok": True, "message": "Organization created. You can now sign in.", "org_id": org.id}
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        log.error(f"Error registering organization: {e}")
        raise HTTPException(status_code=500, detail="Failed to register organization")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/auth/health")
async def health():
    return {"status": "ok", "service": "auth-api", "version": "2.0.0"}


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Exposes metrics in Prometheus text format:
    - http_request_duration_seconds: Request latency histogram
    - http_requests_total: Total request counter
    - http_errors_total: Error counter (5xx responses)
    - db_query_duration_seconds: Database query duration histogram
    
    Scrape with: curl http://localhost:5001/metrics
    """
    return get_metrics()


@app.get("/auth/health/backups")
async def backup_health():
    """
    Check if recent database backups exist and are valid.
    
    Returns backup status:
    - ok: Recent backup exists and is valid
    - warning: Backup exists but is older than threshold
    - critical: No backups found
    """
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    
    try:
        backup_age_hours = int(os.getenv("BACKUP_HEALTH_CHECK_HOURS", "24"))
        
        # Get recent backups
        backups = get_recent_backups(limit=5)
        
        if not backups:
            return {
                "status": "critical",
                "message": "No backups found",
                "backups": [],
            }
        
        # Check age of most recent backup
        latest_backup = backups[0]
        latest_time = datetime.fromisoformat(latest_backup["created_at"])
        backup_age = datetime.now(timezone.utc) - latest_time
        
        if backup_age > timedelta(hours=backup_age_hours):
            return {
                "status": "warning",
                "message": f"Latest backup is {backup_age.days}d {backup_age.seconds//3600}h old",
                "latest_backup": latest_backup["filename"],
                "backup_age_hours": backup_age.total_seconds() / 3600,
                "threshold_hours": backup_age_hours,
                "backups": backups,
            }
        
        return {
            "status": "ok",
            "message": "Recent backups exist",
            "latest_backup": latest_backup["filename"],
            "backup_age_hours": backup_age.total_seconds() / 3600,
            "total_backups": len(backups),
            "backups": backups,
        }
    
    except Exception as e:
        log.error(f"Backup health check failed: {e}")
        return {
            "status": "critical",
            "message": f"Backup health check error: {str(e)}",
        }
