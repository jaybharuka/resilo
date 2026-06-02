"""013_cluster_min_similarity

Adds incident_clusters.min_similarity — weakest pairwise link in the cluster,
used to detect single-linkage chaining.

Revision ID: 013_cluster_min_similarity
Revises: 012_incident_clusters
Create Date: 2026-06-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "013_cluster_min_similarity"
down_revision = "012_incident_clusters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incident_clusters",
        sa.Column("min_similarity", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incident_clusters", "min_similarity")
