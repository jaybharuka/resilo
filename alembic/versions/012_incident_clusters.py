"""012_incident_clusters

Adds incident_clusters and cluster_members tables for the semantic
cross-incident correlation engine (Phase 6).

Revision ID: 012_incident_clusters
Revises: 011_context_evidence
Create Date: 2026-06-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "012_incident_clusters"
down_revision = "011_context_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_clusters",
        sa.Column("id",                        sa.String(36),  primary_key=True),
        sa.Column("org_id",                    sa.String(36),  nullable=False),
        sa.Column("title",                     sa.String(500), nullable=False),
        sa.Column("inferred_root_cause",       sa.Text,        nullable=True),
        sa.Column("status",                    sa.String(20),  nullable=False, server_default="open"),
        sa.Column("severity",                  sa.String(20),  nullable=False, server_default="medium"),
        sa.Column("category",                  sa.String(50),  nullable=True),
        sa.Column("member_count",              sa.Integer,     nullable=False, server_default="0"),
        sa.Column("avg_similarity",            sa.Float,       nullable=True),
        sa.Column("representative_alert_id",   sa.String(36),  nullable=True),
        sa.Column("correlation_method",        sa.String(50),  nullable=False, server_default="semantic"),
        sa.Column("window_start",              sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end",                sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at",               sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",                sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at",                sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_cluster_org_status",  "incident_clusters", ["org_id", "status"])
    op.create_index("ix_cluster_org_created", "incident_clusters", ["org_id", "created_at"])

    op.create_table(
        "cluster_members",
        sa.Column("id",         sa.String(36), primary_key=True),
        sa.Column("cluster_id", sa.String(36), nullable=False),
        sa.Column("org_id",     sa.String(36), nullable=False),
        sa.Column("alert_id",   sa.String(36), nullable=True),
        sa.Column("memory_id",  sa.String(36), nullable=True),
        sa.Column("agent_id",   sa.String(36), nullable=True),
        sa.Column("similarity", sa.Float,      nullable=True),
        sa.Column("root_cause", sa.Text,       nullable=True),
        sa.Column("category",   sa.String(50), nullable=True),
        sa.Column("joined_at",  sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["cluster_id"], ["incident_clusters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_cluster_member_cluster", "cluster_members", ["cluster_id"])
    op.create_index("ix_cluster_member_alert",   "cluster_members", ["alert_id"])
    op.create_index("ix_cluster_member_org",     "cluster_members", ["org_id"])


def downgrade() -> None:
    op.drop_table("cluster_members")
    op.drop_table("incident_clusters")
