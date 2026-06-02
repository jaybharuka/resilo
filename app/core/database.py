"""
database.py â€” PostgreSQL / TimescaleDB models for AIOps Bot (SQLAlchemy 2.0 async)

Shared by: auth_api.py, core_api.py, anomaly_engine.py, notification_service.py

Set DATABASE_URL in .env:
    DATABASE_URL=postgresql+asyncpg://aiops:aiops@localhost:5432/aiops

TimescaleDB is used automatically when the extension is present.
Falls back gracefully to plain PostgreSQL (dev mode).
"""

import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Float, ForeignKey,
                        Index, Integer, String, Text, func, text)
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.org_context import get_current_org_id

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aiops:aiops@localhost:5432/aiops"
)
TIMESCALE_RETENTION_DAYS = int(os.getenv("TIMESCALE_RETENTION_DAYS", "30"))
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

# asyncpg does not accept sslmode/channel_binding as URL parameters.
# Strip them out and pass ssl via connect_args instead.
def _build_engine_args(raw_url: str):
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
    parsed = urlparse(raw_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    ssl_mode = (params.pop("sslmode", [None])[0] or
                params.pop("ssl",     [None])[0])
    params.pop("channel_binding", None)
    clean_url = urlunparse(parsed._replace(
        query=urlencode({k: v[0] for k, v in params.items()})
    ))
    connect_args = {}
    if ssl_mode in ("require", "verify-ca", "verify-full", "true", "1"):
        connect_args["ssl"] = True
    return clean_url, connect_args

_db_url, _connect_args = _build_engine_args(DATABASE_URL)

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    connect_args=_connect_args,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# â”€â”€ Organizations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Organization(Base):
    __tablename__ = "organizations"

    id:         Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name:       Mapped[str]           = mapped_column(String(255), unique=True, nullable=False)
    slug:       Mapped[str]           = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan:       Mapped[str]           = mapped_column(String(30), default="free", nullable=False)  # free|pro|enterprise
    is_active:              Mapped[bool]           = mapped_column(Boolean, default=True, nullable=False)
    settings:               Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ai_confidence_threshold:Mapped[Optional[float]]= mapped_column(Float, nullable=True)  # per-org override; NULL → use global default
    created_at:             Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())


# â”€â”€ Users â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class User(Base):
    __tablename__ = "users"

    id:                   Mapped[str]            = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:               Mapped[Optional[str]]  = mapped_column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    email:                Mapped[str]            = mapped_column(String(255), unique=True, nullable=False, index=True)
    username:             Mapped[str]            = mapped_column(String(100), unique=True, nullable=False)
    hashed_password:      Mapped[str]            = mapped_column(Text, nullable=False)
    # Org-scoped role: admin | devops | viewer | manager | employee | guest
    role:                 Mapped[str]            = mapped_column(String(20), default="employee", nullable=False)
    is_active:            Mapped[bool]           = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    two_factor_secret:    Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    two_factor_enabled:   Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    full_name:            Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    created_at:           Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:           Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login:           Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts:      Mapped[int]                = mapped_column(Integer, default=0, nullable=False)
    locked_until:         Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id:                 Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:            Mapped[str]           = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash: Mapped[str]           = mapped_column(String(64), unique=True, nullable=False)
    family_id:          Mapped[str]           = mapped_column(String(36), nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    expires_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False)
    created_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_address:         Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent:         Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_revoked:         Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="sessions")


# â”€â”€ Invites & Password Reset â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class InviteToken(Base):
    __tablename__ = "invite_tokens"

    id:         Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token:      Mapped[str]           = mapped_column(String(64), unique=True, nullable=False, index=True)
    org_id:     Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    email:      Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role:       Mapped[str]           = mapped_column(String(20), default="viewer", nullable=False)
    created_by: Mapped[str]           = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False)
    used_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by:    Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    note:       Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:    Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str]      = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used:       Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# â”€â”€ Agents (PostgreSQL-backed, replaces in-memory _remote_agents) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class OnboardingToken(Base):
    """Short-lived (5 min), one-time token used by the desktop agent to self-register."""
    __tablename__ = "onboarding_tokens"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token:      Mapped[str]      = mapped_column(String(128), unique=True, nullable=False, index=True)
    org_id:     Mapped[str]      = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label:      Mapped[str]      = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used:       Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Agent(Base):
    """
    Enterprise agent model. Every agent belongs to an org and authenticates
    using X-Agent-Key header (raw key â†’ SHA-256 â†’ key_hash stored here).
    """
    __tablename__ = "agents"

    id:            Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:        Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    label:         Mapped[str]           = mapped_column(String(255), nullable=False)
    key_hash:      Mapped[str]           = mapped_column(String(64), unique=True, nullable=False)  # SHA-256 of raw key
    created_by:    Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    last_seen:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status:        Mapped[str]           = mapped_column(String(20), default="pending", nullable=False)  # pending|online|offline
    platform_info: Mapped[Optional[dict]]= mapped_column(JSON, nullable=True)  # hostname, os, cpu_cores, python_version
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # device owner
    pending_cmds:  Mapped[Optional[list]]= mapped_column(JSON, nullable=True, default=list)  # queue of commands to deliver
    execution_mode:Mapped[str]           = mapped_column(String(20), default="dry_run", nullable=False)  # dry_run|manual_approval|auto_safe
    source:        Mapped[Optional[str]] = mapped_column(String(20), default="agent", nullable=True)  # agent|prometheus|wmi
    is_active:     Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    created_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    metrics:       Mapped[list["MetricSnapshot"]]   = relationship("MetricSnapshot", back_populates="agent", cascade="all, delete-orphan")
    alerts:        Mapped[list["AlertRecord"]]      = relationship("AlertRecord", back_populates="agent")
    remediations:  Mapped[list["RemediationRecord"]]= relationship("RemediationRecord", back_populates="agent")


# â”€â”€ Legacy: keep RemoteAgent for backward compatibility â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RemoteAgent(Base):
    """
    LEGACY — do not use in new code. Use Agent instead.
    Kept only for backward compatibility with api_server.py and old migration path.
    Remove once the old Flask stack is fully decommissioned.
    """
    __tablename__ = "remote_agents"

    agent_id:     Mapped[str]            = mapped_column(String(16), primary_key=True)
    label:        Mapped[str]            = mapped_column(String(255), nullable=False)
    token_hash:   Mapped[str]            = mapped_column(String(64), unique=True, nullable=False)
    created_by:   Mapped[Optional[str]]  = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    last_seen:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status:       Mapped[str]            = mapped_column(String(20), default="pending", nullable=False)
    last_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active:    Mapped[bool]           = mapped_column(Boolean, default=True, nullable=False)
    created_at:   Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())


# â”€â”€ Metrics (TimescaleDB hypertable on timestamp) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MetricSnapshot(Base):
    """
    Time-series metrics from agents. On TimescaleDB, this table is converted
    to a hypertable partitioned by `timestamp`. On plain Postgres, it stays
    as a regular table with a composite index.
    """
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        Index("ix_metric_org_ts", "org_id", "timestamp"),
        Index("ix_metric_agent_ts", "agent_id", "timestamp"),
    )

    id:           Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:       Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    agent_id:     Mapped[str]           = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    timestamp:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    cpu:          Mapped[float]         = mapped_column(Float, nullable=False)
    memory:       Mapped[float]         = mapped_column(Float, nullable=False)
    disk:         Mapped[float]         = mapped_column(Float, nullable=False)
    network_in:   Mapped[int]           = mapped_column(BigInteger, default=0, nullable=False)
    network_out:  Mapped[int]           = mapped_column(BigInteger, default=0, nullable=False)
    temperature:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    load_avg:       Mapped[Optional[str]]   = mapped_column(String(50), nullable=True)
    processes:      Mapped[Optional[int]]   = mapped_column(Integer, nullable=True)
    uptime_secs:    Mapped[Optional[int]]   = mapped_column(Integer, nullable=True)
    extra:          Mapped[Optional[dict]]  = mapped_column(JSON, nullable=True)
    # Extended metrics (Section 5A)
    top_processes:  Mapped[Optional[dict]]  = mapped_column(JSON,    nullable=True)
    swap_percent:   Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    swap_used_gb:   Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    disk_read_mbps: Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    disk_write_mbps:Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    net_established:Mapped[Optional[int]]   = mapped_column(Integer, nullable=True)
    net_close_wait: Mapped[Optional[int]]   = mapped_column(Integer, nullable=True)
    net_time_wait:  Mapped[Optional[int]]   = mapped_column(Integer, nullable=True)
    load_avg_1m:    Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    load_avg_5m:    Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    load_avg_15m:   Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    uptime_hours:   Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    battery_percent:Mapped[Optional[float]] = mapped_column(Float,   nullable=True)
    battery_plugged:Mapped[Optional[bool]]  = mapped_column(Boolean, nullable=True)
    disk_partitions:Mapped[Optional[list]]  = mapped_column(JSON,    nullable=True)

    agent: Mapped["Agent"] = relationship("Agent", back_populates="metrics")


# â”€â”€ Alerts (persistent, replaces in-memory recent_alerts) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AlertRecord(Base):
    __tablename__ = "alert_records"
    __table_args__ = (
        Index("ix_alert_org_status", "org_id", "status"),
    )

    id:            Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:        Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    agent_id:      Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # device owner at alert time
    severity:      Mapped[str]           = mapped_column(String(20), nullable=False)   # critical|high|medium|low|info
    category:      Mapped[str]           = mapped_column(String(50), nullable=False)   # cpu|memory|disk|network|anomaly
    title:         Mapped[str]           = mapped_column(String(255), nullable=False)
    detail:        Mapped[str]           = mapped_column(Text, nullable=False)
    metric_value:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status:            Mapped[str]           = mapped_column(String(20), default="open", nullable=False)  # open|acknowledged|resolved
    resolved_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:        Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    agent:        Mapped[Optional["Agent"]]        = relationship("Agent", back_populates="alerts")
    remediations: Mapped[list["RemediationRecord"]] = relationship("RemediationRecord", back_populates="alert")


# â”€â”€ Remediation History (persistent, replaces in-memory attempts) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RemediationRecord(Base):
    __tablename__ = "remediation_records"

    id:           Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:       Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    alert_id:     Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("alert_records.id", ondelete="SET NULL"), nullable=True)
    agent_id:     Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    action:       Mapped[str]           = mapped_column(String(100), nullable=False)   # clear_cache|kill_process|restart_serviceâ€¦
    params:       Mapped[Optional[dict]]= mapped_column(JSON, nullable=True)
    source:       Mapped[str]           = mapped_column(String(20), default="auto", nullable=False)  # auto|manual
    triggered_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    status:       Mapped[str]           = mapped_column(String(20), default="pending", nullable=False)  # pending|running|success|failed|skipped
    result:       Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error:        Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    before_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_metrics:  Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    verified:     Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)
    started_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    agent: Mapped[Optional["Agent"]]        = relationship("Agent", back_populates="remediations")
    alert: Mapped[Optional["AlertRecord"]]  = relationship("AlertRecord", back_populates="remediations")


# â”€â”€ Audit Log (every significant action is logged here) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RemediationJob(Base):
    __tablename__ = "remediation_jobs"
    __table_args__ = (
        Index("ix_remediation_jobs_org_created", "org_id", "created_at"),
        Index("ix_remediation_jobs_status_created", "status", "created_at"),
    )

    id:            Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:        Mapped[Optional[str]]  = mapped_column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_id:      Mapped[Optional[str]]  = mapped_column(String(36), ForeignKey("alert_records.id", ondelete="SET NULL"), nullable=True, index=True)
    playbook_type: Mapped[str]            = mapped_column(String(100), nullable=False)
    status:        Mapped[str]            = mapped_column(String(20), nullable=False, default="pending")
    attempts:      Mapped[int]            = mapped_column(Integer, nullable=False, default=0)
    max_retries:   Mapped[int]            = mapped_column(Integer, nullable=False, default=3)
    payload:       Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_error:    Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    created_at:    Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at:    Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    # Extended fields for audit and decision tracing
    initiated_by:   Mapped[Optional[str]]  = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    execution_mode: Mapped[Optional[str]]  = mapped_column(String(20), nullable=True)  # dry_run|manual_approval|auto_safe
    decision_source:Mapped[Optional[str]]  = mapped_column(String(50), nullable=True)  # langchain|rule_fallback
    llm_raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    policy_evaluation: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    correlation_id:   Mapped[Optional[str]]  = mapped_column(String(100), nullable=True, index=True)
    scheduled_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_org_ts", "org_id", "created_at"),
    )

    id:            Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:        Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id:       Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    agent_id:      Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action:        Mapped[str]           = mapped_column(String(100), nullable=False)   # user.login|agent.heartbeat|alert.createdâ€¦
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id:   Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    detail:        Mapped[Optional[dict]]= mapped_column(JSON, nullable=True)
    ip_address:    Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent:    Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


# â”€â”€ Notification Channels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class NotificationChannel(Base):
    """
    Stores per-user/org notification channel configuration.
    Each row represents one destination: an email address, a Slack webhook,
    or a Telegram bot+chat pair.

    config examples:
      email:    {"email": "ops@corp.com", "smtp_host": "...", ...}
      slack:    {"webhook_url": "https://hooks.slack.com/..."}
      telegram: {"bot_token": "123:ABC...", "chat_id": "-100..."}
    """
    __tablename__ = "notification_channels"
    __table_args__ = (
        Index("ix_notifch_org", "org_id"),
    )

    id:           Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:       Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id:      Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_type: Mapped[str]           = mapped_column(String(20), nullable=False)   # email | slack | telegram
    label:        Mapped[Optional[str]] = mapped_column(String(100), nullable=True)   # friendly name
    config:       Mapped[dict]          = mapped_column(JSON, nullable=False, default=dict)
    enabled:      Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    # Severity filter â€” only notify for these severities; None means all
    severities:   Mapped[Optional[list]]= mapped_column(JSON, nullable=True)
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CommandWhitelist(Base):
    """
    Per-organization command whitelist and parameter constraints.
    category: safe | medium | dangerous
    allowed_targets: JSON array of allowed target names or patterns (NULL=any)
    allowed_args_schema: JSON schema or descriptor for allowed args (nullable)
    """
    __tablename__ = "command_whitelist"
    __table_args__ = (
        Index("ix_cmdwl_org", "org_id"),
    )

    id:                Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:            Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    command:           Mapped[str]           = mapped_column(String(100), nullable=False)
    category:          Mapped[str]           = mapped_column(String(20), nullable=False, default="safe")
    allowed_targets:   Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    allowed_args_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active:         Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    created_by:        Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at:        Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())


# â”€â”€ Alert Rules â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AlertRule(Base):
    """
    User-defined threshold rules. When a metric crosses the threshold for
    a matching agent (or any agent when agent_id is NULL), an AlertRecord is
    created using this rule's severity and the notification pipeline fires.

    cooldown_minutes: minimum minutes between repeated alerts for the same
                      (org, agent, metric) combination.
    notify_channels:  list of channel_type strings to fan-out to, e.g.
                      ["email", "slack"].  NULL means all enabled channels.
    """
    __tablename__ = "alert_rules"
    __table_args__ = (
        Index("ix_alertrule_org", "org_id"),
    )

    id:               Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:           Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id:         Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)
    name:             Mapped[str]           = mapped_column(String(255), nullable=False)
    metric:           Mapped[str]           = mapped_column(String(20), nullable=False)   # cpu | memory | disk
    threshold:        Mapped[float]         = mapped_column(Float, nullable=False)
    severity:         Mapped[str]           = mapped_column(String(20), nullable=False)   # critical | high | medium | low | info
    cooldown_minutes: Mapped[int]           = mapped_column(Integer, default=15, nullable=False)
    enabled:          Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    notify_channels:  Mapped[Optional[list]]= mapped_column(JSON, nullable=True)          # ["email","slack"] or NULL=all
    created_by:       Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at:       Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:       Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# â”€â”€ Notification Log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class NotificationLog(Base):
    """
    Immutable audit trail of every notification attempt (alert or daily summary).
    status: sent | failed
    notification_type: alert | summary
    """
    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notiflog_org_ts", "org_id", "sent_at"),
    )

    id:                Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:            Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    alert_id:          Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("alert_records.id", ondelete="SET NULL"), nullable=True)
    channel_id:        Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("notification_channels.id", ondelete="SET NULL"), nullable=True)
    channel_type:      Mapped[str]           = mapped_column(String(20), nullable=False)
    notification_type: Mapped[str]           = mapped_column(String(20), default="alert", nullable=False)  # alert | summary
    recipient:         Mapped[Optional[str]] = mapped_column(String(255), nullable=True)   # email addr, chat_id, or webhook hint
    subject:           Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status:            Mapped[str]           = mapped_column(String(20), default="sent", nullable=False)
    error:             Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at:           Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


# â”€â”€ WMI Targets (agentless Windows polling) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class WMITarget(Base):
    """
    Stores credentials for agentless Windows machine monitoring via WinRM/WMI.
    The server polls each target on a schedule and stores results as MetricSnapshot
    under the linked agent_id. Password is Fernet-encrypted at rest.
    """
    __tablename__ = "wmi_targets"
    __table_args__ = (
        Index("ix_wmitarget_org", "org_id"),
    )

    id:             Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:         Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id:       Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    label:          Mapped[str]           = mapped_column(String(255), nullable=False)
    host:           Mapped[str]           = mapped_column(String(255), nullable=False)   # IP or hostname
    port:           Mapped[int]           = mapped_column(Integer, default=5985, nullable=False)
    username:       Mapped[str]           = mapped_column(String(255), nullable=False)
    enc_password:   Mapped[str]           = mapped_column(Text, nullable=False)          # Fernet-encrypted
    is_active:      Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    last_polled:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status:    Mapped[str]           = mapped_column(String(20), default="pending", nullable=False)  # pending|ok|error
    last_error:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by:     Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at:     Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())


# â”€â”€ WMI Bootstrap Invites (zero-input onboarding) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class WmiInvite(Base):
    """
    One-time invite token for zero-input Windows machine self-registration.
    Admin generates a token â†’ PowerShell command is sent to the user â†’
    user runs it on their machine â†’ machine auto-registers as a WMI target.
    Token is SHA-256 hashed at rest; raw token is never stored.
    """
    __tablename__ = "wmi_invites"
    __table_args__ = (
        Index("ix_wmiinvite_org", "org_id"),
    )

    id:                  Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:              Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    token_hash:          Mapped[str]           = mapped_column(String(64), nullable=False, unique=True)  # SHA-256 hex
    created_by:          Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    expires_at:          Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False)
    used:                Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)
    used_at:             Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_agent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    machine_label:       Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at:          Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Incidents (declared via dashboard "Declare Incident" button) ─────────────

class Incident(Base):
    """
    Persistent incident record. One active incident per org at a time.
    status: active | resolved
    """
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incident_org_status", "org_id", "status"),
    )

    id:           Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:       Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    severity:     Mapped[str]           = mapped_column(String(10), nullable=False)   # SEV1|SEV2|SEV3|SEV4
    service:      Mapped[str]           = mapped_column(String(100), nullable=False)
    description:  Mapped[str]           = mapped_column(Text, nullable=False)
    commander:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    declared_by:  Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status:       Mapped[str]           = mapped_column(String(20), default="active", nullable=False)   # active|resolved
    declared_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    resolved_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by:  Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    timeline:     Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)  # [{ts, actor, note}]


# ── Agent Action Log (auto-execution audit + rate limiting) ──────────────────

class AgentActionLog(Base):
    """
    Immutable record of every action auto-executed in auto_safe mode.
    Used to enforce MAX_AUTO_RESTARTS_PER_HOUR rate limit.
    """
    __tablename__ = "agent_action_log"
    __table_args__ = (
        Index("ix_agentactionlog_agent_created", "agent_id", "created_at"),
    )

    id:                Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:            Mapped[Optional[str]]  = mapped_column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_id:          Mapped[str]            = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    remediation_job_id:Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("remediation_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    action:            Mapped[str]            = mapped_column(String(100), nullable=False)
    target:            Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    initiated_by:      Mapped[Optional[str]]  = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    execution_mode:    Mapped[Optional[str]]  = mapped_column(String(20), nullable=True)
    decision_source:   Mapped[Optional[str]]  = mapped_column(String(50), nullable=True)
    llm_raw_response:  Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    policy_evaluation: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status:            Mapped[str]            = mapped_column(String(20), default="queued", nullable=False)  # queued|started|completed|failed|rejected
    success:           Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    exit_code:         Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    stdout:            Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    stderr:            Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    correlation_id:    Mapped[Optional[str]]  = mapped_column(String(100), nullable=True, index=True)
    metadata_json:     Mapped[Optional[str]]  = mapped_column(Text, nullable=True)   # JSON blob for AI decisions and feedback records
    created_at:        Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship helper
    remediation_job:   Mapped[Optional["RemediationJob"]] = relationship("RemediationJob", backref="action_logs")


# ── Incident Memory (historical knowledge base) ───────────────────────────────

class IncidentMemory(Base):
    """
    Persistent knowledge base entry for every completed AI investigation.
    Used by find_similar_incidents() to enrich future LLM prompts with
    historical context before calling Gemini.
    """
    __tablename__ = "incident_memory"
    __table_args__ = (
        Index("ix_incmem_org_category", "org_id", "category"),
        Index("ix_incmem_org_created", "org_id", "created_at"),
    )

    id:                 Mapped[str]            = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:             Mapped[str]            = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    incident_id:        Mapped[Optional[str]]  = mapped_column(String(100), nullable=True, index=True)
    alert_id:           Mapped[Optional[str]]  = mapped_column(String(36), nullable=True)
    agent_id:           Mapped[Optional[str]]  = mapped_column(String(36), nullable=True, index=True)
    title:              Mapped[str]            = mapped_column(String(500), nullable=False)
    severity:           Mapped[str]            = mapped_column(String(20), nullable=False)
    category:           Mapped[str]            = mapped_column(String(50), nullable=False)          # cpu|memory|disk|network|fleet
    metrics_snapshot:   Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)                # {cpu, memory, disk, load_avg_1m, ...}
    root_cause:         Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    reasoning:          Mapped[Optional[str]]  = mapped_column(Text, nullable=True)                # full LLM chain-of-thought
    hypotheses:         Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)  # [{cause, confidence, evidence}]
    recommended_action: Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    executed_action:    Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    success:            Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    resolution_time:    Mapped[Optional[float]]= mapped_column(Float, nullable=True)               # seconds from first alert to resolve
    tags:               Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)  # keyword tags for similarity scoring
    # ── Semantic embedding (Phase 2) ──────────────────────────────────────────
    embedding:              Mapped[Optional[list]]  = mapped_column(JSON, nullable=True)            # float[] — Gemini text-embedding-004
    embedding_model:        Mapped[Optional[str]]   = mapped_column(String(100), nullable=True)     # e.g. "text-embedding-004"
    embedding_created_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:         Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    resolved_at:        Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ── InvestigationFeedback (root cause accuracy tracking) ──────────────────────

class IncidentCluster(Base):
    """
    A group of alerts/investigations sharing a common root cause,
    discovered by the semantic correlation engine.

    Lifecycle: open → investigating → resolved | dismissed
    """
    __tablename__ = "incident_clusters"
    __table_args__ = (
        Index("ix_cluster_org_status", "org_id", "status"),
        Index("ix_cluster_org_created", "org_id", "created_at"),
    )

    id:               Mapped[str]            = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:           Mapped[str]            = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    title:            Mapped[str]            = mapped_column(String(500), nullable=False)
    inferred_root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status:           Mapped[str]            = mapped_column(String(20), default="open", nullable=False)  # open|investigating|resolved|dismissed
    severity:         Mapped[str]            = mapped_column(String(20), default="medium", nullable=False)
    category:         Mapped[Optional[str]]  = mapped_column(String(50), nullable=True)   # dominant incident type
    member_count:     Mapped[int]            = mapped_column(Integer, default=0, nullable=False)
    avg_similarity:   Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    min_similarity:   Mapped[Optional[float]]= mapped_column(Float, nullable=True)   # weakest pairwise link — chaining indicator
    representative_alert_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # most central member
    correlation_method: Mapped[str]          = mapped_column(String(50), default="semantic", nullable=False)  # semantic|metric|hybrid
    window_start:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:       Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at:       Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    members: Mapped[list["ClusterMember"]] = relationship("ClusterMember", back_populates="cluster", cascade="all, delete-orphan")


class ClusterMember(Base):
    """
    A single alert or investigation that belongs to an IncidentCluster.
    """
    __tablename__ = "cluster_members"
    __table_args__ = (
        Index("ix_cluster_member_cluster", "cluster_id"),
        Index("ix_cluster_member_alert", "alert_id"),
    )

    id:            Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cluster_id:    Mapped[str]           = mapped_column(String(36), ForeignKey("incident_clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id:        Mapped[str]           = mapped_column(String(36), nullable=False, index=True)
    alert_id:      Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    memory_id:     Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    agent_id:      Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    similarity:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # cosine similarity to cluster centroid
    root_cause:    Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category:      Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    joined_at:     Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cluster: Mapped["IncidentCluster"] = relationship("IncidentCluster", back_populates="members")


class InvestigationFeedback(Base):
    """
    Human or automated feedback on investigation root cause accuracy.
    Drives accuracy metrics and future embedding fine-tuning.
    """
    __tablename__ = "investigation_feedback"
    __table_args__ = (
        Index("ix_inv_feedback_org_created", "org_id", "created_at"),
        Index("ix_inv_feedback_investigation", "investigation_id"),
    )

    id:                     Mapped[str]            = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:                 Mapped[str]            = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    investigation_id:       Mapped[str]            = mapped_column(String(100), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False)
    agent_id:               Mapped[Optional[str]]  = mapped_column(String(36), nullable=True)
    incident_type:          Mapped[Optional[str]]  = mapped_column(String(50), nullable=True)       # cpu|memory|disk|fleet
    confidence_bucket:      Mapped[Optional[str]]  = mapped_column(String(20), nullable=True)       # high|medium|low
    predicted_root_cause:   Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    actual_root_cause:      Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    correct:                Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)          # True=accurate, False=wrong, None=unknown
    predicted_action:       Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    actual_action:          Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    action_correct:         Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    submitted_by:           Mapped[Optional[str]]  = mapped_column(String(36), nullable=True)       # user_id or "system"
    note:                   Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    created_at:             Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── LogEntry (agent log lines for investigation context) ─────────────────────

class LogEntry(Base):
    """
    Recent log lines collected from an agent during an incident.
    Stores up to 500 lines per incident window; purged after 7 days.
    Used by log_collector.py to enrich investigation evidence.
    """
    __tablename__ = "log_entries"
    __table_args__ = (
        Index("ix_logentry_agent_collected", "agent_id", "collected_at"),
        Index("ix_logentry_org_collected",   "org_id",   "collected_at"),
    )

    id:           Mapped[str]           = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id:       Mapped[str]           = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    agent_id:     Mapped[str]           = mapped_column(String(36), nullable=False, index=True)
    alert_id:     Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    source:       Mapped[str]           = mapped_column(String(100), nullable=False)    # syslog|journald|app|windows_event
    level:        Mapped[str]           = mapped_column(String(20),  nullable=False)    # ERROR|WARN|INFO|DEBUG
    message:      Mapped[str]           = mapped_column(Text, nullable=False)
    raw_line:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    log_ts:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # original timestamp from log line


# ── Investigation (multi-stage AI investigation workflow) ─────────────────────

class Investigation(Base):
    """
    Tracks a single multi-stage AI investigation lifecycle from alert detection
    through evidence collection, hypothesis generation, root cause analysis,
    and action planning.

    Stages: EVIDENCE_COLLECTION → HISTORICAL_ANALYSIS → HYPOTHESIS_GENERATION
            → ROOT_CAUSE_ANALYSIS → ACTION_PLANNING → completed
    """
    __tablename__ = "investigations"
    __table_args__ = (
        Index("ix_investigation_org_status", "org_id", "status"),
        Index("ix_investigation_agent_created", "agent_id", "created_at"),
    )

    id:                 Mapped[str]            = mapped_column(String(100), primary_key=True)      # INV-YYYYMMDD-XXXXXX
    org_id:             Mapped[str]            = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id:           Mapped[str]            = mapped_column(String(36), nullable=False, index=True)
    alert_id:           Mapped[Optional[str]]  = mapped_column(String(36), nullable=True, index=True)
    incident_id:        Mapped[Optional[str]]  = mapped_column(String(100), nullable=True, index=True)
    status:             Mapped[str]            = mapped_column(String(20), default="running", nullable=False)   # running|completed|failed
    stage:              Mapped[str]            = mapped_column(String(30), default="EVIDENCE_COLLECTION", nullable=False)
    evidence:           Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    similar_incidents:  Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    hypotheses:         Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    root_cause:         Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    recommended_action: Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    confidence:         Mapped[float]          = mapped_column(Float, default=0.0, nullable=False)
    action_routing:     Mapped[Optional[str]]  = mapped_column(String(30), nullable=True)          # auto_execute|manual_approval|investigation_only
    timeline:           Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)  # [{timestamp, event}]
    # ── Semantic retrieval telemetry (Phase 2) ─────────────────────────────────
    semantic_hits:              Mapped[Optional[int]]   = mapped_column(nullable=True)              # number of embedding matches above threshold
    avg_similarity:             Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # mean cosine similarity of retrieved memories
    retrieval_time_ms:          Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # ms spent in memory search
    memories_used_in_reasoning: Mapped[Optional[int]]   = mapped_column(nullable=True)              # how many retrieved memories referenced in final RCA
    # ── Dynamic context evidence (Phase 4) ─────────────────────────────────────
    context_evidence:           Mapped[Optional[dict]]  = mapped_column(JSON, nullable=True)         # {process_tree, oom_history, pg_connections, ...}
    # ── LLM cost telemetry (Phase 5) ────────────────────────────────────────────
    llm_cost:                   Mapped[Optional[dict]]  = mapped_column(JSON, nullable=True)         # {llm_calls, est_tokens, total_llm_ms, avg_llm_ms}
    evidence_contribution:      Mapped[Optional[dict]]  = mapped_column(JSON, nullable=True)         # {logs_helped, memory_helped, context_helped, planner_helped}
    created_at:         Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


async def wait_for_db() -> None:
    """
    Retry the database connection until it succeeds or retries are exhausted.

    Reads:
      DB_CONNECT_RETRIES     â€” max attempts  (default 5)
      DB_CONNECT_RETRY_DELAY â€” seconds between attempts (default 3)

    Logs a clear message per attempt and exits the process with code 1 if
    all retries are exhausted â€” never starts the app with no DB.
    """
    import asyncio
    import logging
    import sys

    from sqlalchemy import text as _text

    _log = logging.getLogger("database")
    retries = int(os.getenv("DB_CONNECT_RETRIES", "5"))
    delay   = float(os.getenv("DB_CONNECT_RETRY_DELAY", "3"))

    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(_text("SELECT 1"))
            _log.info("Database connection established (attempt %d/%d)", attempt, retries)
            return
        except Exception as exc:
            if attempt < retries:
                _log.warning(
                    "DB not ready, retrying in %.0fs (attempt %d/%d): %s",
                    delay, attempt, retries, exc,
                )
                await asyncio.sleep(delay)
            else:
                _log.error(
                    "Database unreachable after %d attempt(s). Exiting. Last error: %s",
                    retries, exc,
                )
                sys.exit(1)


async def init_db() -> None:
    """
    Configure runtime DB policies after Alembic has created schema.
    Safe to call on every startup â€” call wait_for_db() first.
    """
    import logging
    log = logging.getLogger("database")

    # Ensure all ORM models have tables (checkfirst=True → safe on every restart)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    # Retention policy is kept in application code because it is driven by
    # TIMESCALE_RETENTION_DAYS, an operator-configurable env var.
    if TIMESCALE_RETENTION_DAYS > 0:
        async with engine.begin() as conn:
            try:
                await conn.execute(
                    __import__("sqlalchemy").text(
                        f"SELECT add_retention_policy('metric_snapshots', "
                        f"INTERVAL '{TIMESCALE_RETENTION_DAYS} days', if_not_exists => TRUE)"
                    )
                )
                log.info("TimescaleDB retention policy set: %d days", TIMESCALE_RETENTION_DAYS)
            except Exception:
                pass  # TimescaleDB not available â€” plain PostgreSQL mode


async def get_db():
    """FastAPI dependency — yields an async session."""
    async with SessionLocal() as session:
        try:
            org_id = get_current_org_id()
            if org_id:
                # Transaction-local scope avoids leakage across pooled connections.
                await session.execute(
                    text("SELECT set_config('app.current_org', :org_id, true)"),
                    {"org_id": org_id},
                )
            yield session
        finally:
            await session.close()
