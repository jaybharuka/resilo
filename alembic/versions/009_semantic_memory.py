"""009_semantic_memory

Adds:
  incident_memory : embedding, embedding_model, embedding_created_at
  investigations  : semantic_hits, avg_similarity, retrieval_time_ms
  investigation_feedback : new table

Revision ID: 009_semantic_memory
Revises: 008_investigation_engine
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "009_semantic_memory"
down_revision = "008_investigation_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── incident_memory: add embedding columns ────────────────────────────────
    op.add_column("incident_memory",
        sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column("incident_memory",
        sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("incident_memory",
        sa.Column("embedding_created_at", sa.DateTime(timezone=True), nullable=True))

    # ── investigations: add semantic telemetry columns ────────────────────────
    op.add_column("investigations",
        sa.Column("semantic_hits", sa.Integer(), nullable=True))
    op.add_column("investigations",
        sa.Column("avg_similarity", sa.Float(), nullable=True))
    op.add_column("investigations",
        sa.Column("retrieval_time_ms", sa.Float(), nullable=True))

    # ── investigation_feedback: new table ─────────────────────────────────────
    op.create_table(
        "investigation_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("investigation_id", sa.String(100),
                  sa.ForeignKey("investigations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("agent_id",            sa.String(36),  nullable=True),
        sa.Column("incident_type",       sa.String(50),  nullable=True),
        sa.Column("confidence_bucket",   sa.String(20),  nullable=True),
        sa.Column("predicted_root_cause", sa.Text(),     nullable=True),
        sa.Column("actual_root_cause",   sa.Text(),      nullable=True),
        sa.Column("correct",             sa.Boolean(),   nullable=True),
        sa.Column("predicted_action",    sa.String(100), nullable=True),
        sa.Column("actual_action",       sa.String(100), nullable=True),
        sa.Column("action_correct",      sa.Boolean(),   nullable=True),
        sa.Column("submitted_by",        sa.String(36),  nullable=True),
        sa.Column("note",                sa.Text(),      nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inv_feedback_org_created",
                    "investigation_feedback", ["org_id", "created_at"])
    op.create_index("ix_inv_feedback_investigation",
                    "investigation_feedback", ["investigation_id"])


def downgrade() -> None:
    op.drop_table("investigation_feedback")
    op.drop_column("investigations",   "retrieval_time_ms")
    op.drop_column("investigations",   "avg_similarity")
    op.drop_column("investigations",   "semantic_hits")
    op.drop_column("incident_memory",  "embedding_created_at")
    op.drop_column("incident_memory",  "embedding_model")
    op.drop_column("incident_memory",  "embedding")
