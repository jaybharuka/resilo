"""010_log_intelligence

Adds:
  log_entries                        : new table (Phase 3 Log Intelligence)
  investigations.memories_used_in_reasoning : new column (memory usefulness)

Revision ID: 010_log_intelligence
Revises: 009_semantic_memory
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "010_log_intelligence"
down_revision = "009_semantic_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── log_entries ───────────────────────────────────────────────────────────
    op.create_table(
        "log_entries",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("org_id",       sa.String(36),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("agent_id",     sa.String(36),  nullable=False),
        sa.Column("alert_id",     sa.String(36),  nullable=True),
        sa.Column("source",       sa.String(100), nullable=False),
        sa.Column("level",        sa.String(20),  nullable=False),
        sa.Column("message",      sa.Text(),      nullable=False),
        sa.Column("raw_line",     sa.Text(),      nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("log_ts",       sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_logentry_agent_collected", "log_entries",
                    ["agent_id", "collected_at"])
    op.create_index("ix_logentry_org_collected",   "log_entries",
                    ["org_id",   "collected_at"])
    op.create_index("ix_logentry_alert",           "log_entries",
                    ["alert_id"])

    # ── investigations: memory usefulness ─────────────────────────────────────
    op.add_column("investigations",
        sa.Column("memories_used_in_reasoning", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("investigations", "memories_used_in_reasoning")
    op.drop_table("log_entries")
