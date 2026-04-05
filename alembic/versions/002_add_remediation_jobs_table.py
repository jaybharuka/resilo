"""Add remediation_jobs table for durable remediation queue.

Revision ID: 002
Revises: 001
Create Date: 2026-04-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "remediation_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "alert_id",
            sa.String(36),
            sa.ForeignKey("alert_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("playbook_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
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
    op.create_index("ix_remediation_jobs_alert_id", "remediation_jobs", ["alert_id"])
    op.create_index(
        "ix_remediation_jobs_status_created",
        "remediation_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_remediation_jobs_status_created", table_name="remediation_jobs")
    op.drop_index("ix_remediation_jobs_alert_id", table_name="remediation_jobs")
    op.drop_table("remediation_jobs")
