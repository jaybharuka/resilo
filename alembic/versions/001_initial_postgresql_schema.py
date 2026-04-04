"""Initial PostgreSQL schema for AIOps Bot.

Revision ID: 001
Revises:
Create Date: 2026-03-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── organizations ──────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("plan", sa.String(30), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("settings", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="employee"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "must_change_password",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("two_factor_secret", sa.Text, nullable=True),
        sa.Column(
            "two_factor_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_org_id", "users", ["org_id"])

    # ── user_sessions ──────────────────────────────────────────────────────────
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column(
            "is_revoked",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    # ── invite_tokens ──────────────────────────────────────────────────────────
    op.create_table(
        "invite_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.String(36), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_invite_tokens_token", "invite_tokens", ["token"])
    op.create_index("ix_invite_tokens_org_id", "invite_tokens", ["org_id"])

    # ── password_reset_tokens ──────────────────────────────────────────────────
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── agents ─────────────────────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("platform_info", sa.JSON, nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pending_cmds", sa.JSON, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_agents_org_id", "agents", ["org_id"])
    op.create_index("ix_agents_owner_user_id", "agents", ["owner_user_id"])

    # ── remote_agents (legacy Flask compatibility) ─────────────────────────────
    op.create_table(
        "remote_agents",
        sa.Column("agent_id", sa.String(16), primary_key=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("last_metrics", sa.JSON, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── metric_snapshots ───────────────────────────────────────────────────────
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu", sa.Float, nullable=False),
        sa.Column("memory", sa.Float, nullable=False),
        sa.Column("disk", sa.Float, nullable=False),
        sa.Column("network_in", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("network_out", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("temperature", sa.Float, nullable=True),
        sa.Column("load_avg", sa.String(50), nullable=True),
        sa.Column("processes", sa.Integer, nullable=True),
        sa.Column("uptime_secs", sa.Integer, nullable=True),
        sa.Column("extra", sa.JSON, nullable=True),
    )
    op.create_index("ix_metric_snapshots_timestamp", "metric_snapshots", ["timestamp"])
    op.create_index("ix_metric_org_ts", "metric_snapshots", ["org_id", "timestamp"])
    op.create_index("ix_metric_agent_ts", "metric_snapshots", ["agent_id", "timestamp"])
    # Convert to TimescaleDB hypertable and enable 7-day compression when available.
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
            PERFORM create_hypertable(
                'metric_snapshots',
                'timestamp',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );

            ALTER TABLE metric_snapshots SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'org_id,agent_id',
                timescaledb.compress_orderby = 'timestamp DESC'
            );

            PERFORM add_compression_policy(
                'metric_snapshots',
                compress_after => INTERVAL '7 days',
                if_not_exists => TRUE
            );
        EXCEPTION
            WHEN undefined_function OR feature_not_supported OR invalid_parameter_value THEN
                NULL;
        END $$;
        """
    )

    # ── alert_records ──────────────────────────────────────────────────────────
    op.create_table(
        "alert_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
        sa.Column("metric_value", sa.Float, nullable=True),
        sa.Column("threshold", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_alert_records_org_id", "alert_records", ["org_id"])
    op.create_index("ix_alert_records_agent_id", "alert_records", ["agent_id"])
    op.create_index("ix_alert_records_owner_user_id", "alert_records", ["owner_user_id"])
    op.create_index("ix_alert_records_created_at", "alert_records", ["created_at"])
    op.create_index("ix_alert_org_status", "alert_records", ["org_id", "status"])

    # ── remediation_records ────────────────────────────────────────────────────
    op.create_table(
        "remediation_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "alert_id",
            sa.String(36),
            sa.ForeignKey("alert_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("params", sa.JSON, nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="auto"),
        sa.Column(
            "triggered_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("before_metrics", sa.JSON, nullable=True),
        sa.Column("after_metrics", sa.JSON, nullable=True),
        sa.Column(
            "verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_remediation_records_org_id", "remediation_records", ["org_id"])
    op.create_index("ix_remediation_records_created_at", "remediation_records", ["created_at"])

    # ── audit_logs ─────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("agent_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("detail", sa.JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_org_ts", "audit_logs", ["org_id", "created_at"])

    # ── notification_channels ──────────────────────────────────────────────────
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("severities", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_notifch_org", "notification_channels", ["org_id"])
    op.create_index("ix_notification_channels_user_id", "notification_channels", ["user_id"])

    # ── alert_rules ────────────────────────────────────────────────────────────
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(20), nullable=False),
        sa.Column("threshold", sa.Float, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("cooldown_minutes", sa.Integer, nullable=False, server_default="15"),
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("notify_channels", sa.JSON, nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_alertrule_org", "alert_rules", ["org_id"])

    # ── notification_logs ──────────────────────────────────────────────────────
    op.create_table(
        "notification_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "alert_id",
            sa.String(36),
            sa.ForeignKey("alert_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "channel_id",
            sa.String(36),
            sa.ForeignKey("notification_channels.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column(
            "notification_type",
            sa.String(20),
            nullable=False,
            server_default="alert",
        ),
        sa.Column("recipient", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_notification_logs_org_id", "notification_logs", ["org_id"])
    op.create_index("ix_notification_logs_sent_at", "notification_logs", ["sent_at"])
    op.create_index("ix_notiflog_org_ts", "notification_logs", ["org_id", "sent_at"])

    # ── wmi_targets ────────────────────────────────────────────────────────────
    op.create_table(
        "wmi_targets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, nullable=False, server_default="5985"),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("enc_password", sa.Text, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_polled", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_wmitarget_org", "wmi_targets", ["org_id"])

    # ── wmi_invites ────────────────────────────────────────────────────────────
    op.create_table(
        "wmi_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "registered_agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("machine_label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_wmiinvite_org", "wmi_invites", ["org_id"])


def downgrade() -> None:
    # Drop indexes before their tables (explicit for offline SQL scripts).
    op.drop_index("ix_wmiinvite_org", table_name="wmi_invites")
    op.drop_table("wmi_invites")

    op.drop_index("ix_wmitarget_org", table_name="wmi_targets")
    op.drop_table("wmi_targets")

    op.drop_index("ix_notiflog_org_ts", table_name="notification_logs")
    op.drop_index("ix_notification_logs_sent_at", table_name="notification_logs")
    op.drop_index("ix_notification_logs_org_id", table_name="notification_logs")
    op.drop_table("notification_logs")

    op.drop_index("ix_alertrule_org", table_name="alert_rules")
    op.drop_table("alert_rules")

    op.drop_index("ix_notification_channels_user_id", table_name="notification_channels")
    op.drop_index("ix_notifch_org", table_name="notification_channels")
    op.drop_table("notification_channels")

    op.drop_index("ix_audit_org_ts", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_remediation_records_created_at", table_name="remediation_records")
    op.drop_index("ix_remediation_records_org_id", table_name="remediation_records")
    op.drop_table("remediation_records")

    op.drop_index("ix_alert_org_status", table_name="alert_records")
    op.drop_index("ix_alert_records_created_at", table_name="alert_records")
    op.drop_index("ix_alert_records_owner_user_id", table_name="alert_records")
    op.drop_index("ix_alert_records_agent_id", table_name="alert_records")
    op.drop_index("ix_alert_records_org_id", table_name="alert_records")
    op.drop_table("alert_records")

    op.drop_index("ix_metric_agent_ts", table_name="metric_snapshots")
    op.drop_index("ix_metric_org_ts", table_name="metric_snapshots")
    op.drop_index("ix_metric_snapshots_timestamp", table_name="metric_snapshots")
    op.drop_table("metric_snapshots")

    op.drop_table("remote_agents")

    op.drop_index("ix_agents_owner_user_id", table_name="agents")
    op.drop_index("ix_agents_org_id", table_name="agents")
    op.drop_table("agents")

    op.drop_table("password_reset_tokens")

    op.drop_index("ix_invite_tokens_org_id", table_name="invite_tokens")
    op.drop_index("ix_invite_tokens_token", table_name="invite_tokens")
    op.drop_table("invite_tokens")

    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
