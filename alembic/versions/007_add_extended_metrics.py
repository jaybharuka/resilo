"""add_extended_metrics

Revision ID: 007_add_extended_metrics
Revises: 6540e6ee8ea8
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_add_extended_metrics"
down_revision = "6540e6ee8ea8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MetricSnapshot — 15 extended columns
    for col_name, col_type in [
        ("top_processes",   sa.JSON()),
        ("swap_percent",    sa.Float()),
        ("swap_used_gb",    sa.Float()),
        ("disk_read_mbps",  sa.Float()),
        ("disk_write_mbps", sa.Float()),
        ("net_established", sa.Integer()),
        ("net_close_wait",  sa.Integer()),
        ("net_time_wait",   sa.Integer()),
        ("load_avg_1m",     sa.Float()),
        ("load_avg_5m",     sa.Float()),
        ("load_avg_15m",    sa.Float()),
        ("uptime_hours",    sa.Float()),
        ("battery_percent", sa.Float()),
        ("battery_plugged", sa.Boolean()),
        ("disk_partitions", sa.JSON()),
    ]:
        op.add_column("metric_snapshots", sa.Column(col_name, col_type, nullable=True))

    # AlertRecord — resolution_reason
    op.add_column("alert_records", sa.Column("resolution_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_records", "resolution_reason")
    for col_name in reversed([
        "top_processes", "swap_percent", "swap_used_gb", "disk_read_mbps", "disk_write_mbps",
        "net_established", "net_close_wait", "net_time_wait", "load_avg_1m", "load_avg_5m",
        "load_avg_15m", "uptime_hours", "battery_percent", "battery_plugged", "disk_partitions",
    ]):
        op.drop_column("metric_snapshots", col_name)
