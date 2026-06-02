"""011_context_evidence

Adds investigations.context_evidence (Phase 4 dynamic context collection)

Revision ID: 011_context_evidence
Revises: 010_log_intelligence
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "011_context_evidence"
down_revision = "010_log_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("context_evidence", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("investigations", "context_evidence")
