"""add_investigation_engine

Creates two new tables:
  - incident_memory   : persistent AI knowledge base for historical incident recall
  - investigations    : multi-stage investigation lifecycle tracking

Revision ID: 008_investigation_engine
Revises: 007_add_extended_metrics
Create Date: 2026-06-02 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_investigation_engine"
down_revision = "007_add_extended_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── incident_memory ───────────────────────────────────────────────────────
    op.create_table(
        "incident_memory",
        sa.Column("id",                 sa.String(36),  nullable=False),
        sa.Column("org_id",             sa.String(36),  nullable=False),
        sa.Column("incident_id",        sa.String(100), nullable=True),
        sa.Column("alert_id",           sa.String(36),  nullable=True),
        sa.Column("agent_id",           sa.String(36),  nullable=True),
        sa.Column("title",              sa.String(500), nullable=False),
        sa.Column("severity",           sa.String(20),  nullable=False),
        sa.Column("category",           sa.String(50),  nullable=False),
        sa.Column("metrics_snapshot",   sa.JSON(),      nullable=True),
        sa.Column("root_cause",         sa.Text(),      nullable=True),
        sa.Column("reasoning",          sa.Text(),      nullable=True),
        sa.Column("hypotheses",         sa.JSON(),      nullable=True),
        sa.Column("recommended_action", sa.String(100), nullable=True),
        sa.Column("executed_action",    sa.String(100), nullable=True),
        sa.Column("success",            sa.Boolean(),   nullable=True),
        sa.Column("resolution_time",    sa.Float(),     nullable=True),
        sa.Column("tags",               sa.JSON(),      nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at",        sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incmem_org_category", "incident_memory", ["org_id", "category"])
    op.create_index("ix_incmem_org_created",  "incident_memory", ["org_id", "created_at"])
    op.create_index("ix_incmem_incident_id",  "incident_memory", ["incident_id"])
    op.create_index("ix_incmem_agent_id",     "incident_memory", ["agent_id"])

    # ── investigations ────────────────────────────────────────────────────────
    op.create_table(
        "investigations",
        sa.Column("id",                 sa.String(100), nullable=False),
        sa.Column("org_id",             sa.String(36),  nullable=False),
        sa.Column("agent_id",           sa.String(36),  nullable=False),
        sa.Column("alert_id",           sa.String(36),  nullable=True),
        sa.Column("incident_id",        sa.String(100), nullable=True),
        sa.Column("status",             sa.String(20),  nullable=False, server_default="running"),
        sa.Column("stage",              sa.String(30),  nullable=False, server_default="EVIDENCE_COLLECTION"),
        sa.Column("evidence",           sa.JSON(),      nullable=True),
        sa.Column("similar_incidents",  sa.JSON(),      nullable=True),
        sa.Column("hypotheses",         sa.JSON(),      nullable=True),
        sa.Column("root_cause",         sa.JSON(),      nullable=True),
        sa.Column("recommended_action", sa.String(100), nullable=True),
        sa.Column("confidence",         sa.Float(),     nullable=False, server_default="0.0"),
        sa.Column("action_routing",     sa.String(30),  nullable=True),
        sa.Column("timeline",           sa.JSON(),      nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at",       sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_investigation_org_status",    "investigations", ["org_id", "status"])
    op.create_index("ix_investigation_agent_created", "investigations", ["agent_id", "created_at"])
    op.create_index("ix_investigation_alert_id",      "investigations", ["alert_id"])
    op.create_index("ix_investigation_incident_id",   "investigations", ["incident_id"])


def downgrade() -> None:
    op.drop_table("investigations")
    op.drop_table("incident_memory")
