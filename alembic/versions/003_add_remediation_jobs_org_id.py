"""Add org_id to remediation_jobs for tenant scoping.

Revision ID: 003
Revises: 002
Create Date: 2026-04-05

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "remediation_jobs",
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_remediation_jobs_org_id", "remediation_jobs", ["org_id"])
    op.create_index(
        "ix_remediation_jobs_org_created",
        "remediation_jobs",
        ["org_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_remediation_jobs_org_created", table_name="remediation_jobs")
    op.drop_index("ix_remediation_jobs_org_id", table_name="remediation_jobs")
    op.drop_column("remediation_jobs", "org_id")
