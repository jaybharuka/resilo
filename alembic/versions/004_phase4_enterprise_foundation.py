"""Phase 4 enterprise foundation: RLS, pricing, SSO, audit extensions.

Revision ID: 004
Revises: 003
Create Date: 2026-04-06

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO organizations (id, name, slug, plan, is_active)
            SELECT :org_id, 'Default Organization', 'default-org', 'starter', true
            WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE id = :org_id)
            """
        ).bindparams(org_id=DEFAULT_ORG_ID)
    )

    op.create_table(
        "pricing_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(30), nullable=False, unique=True),
        sa.Column("service_limit", sa.Integer, nullable=True),
        sa.Column("sso_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("api_limit", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.execute(
        """
        INSERT INTO pricing_plans (id, name, service_limit, sso_enabled, api_limit)
        VALUES
          ('11111111-1111-1111-1111-111111111111', 'starter', 10, false, 100000),
          ('22222222-2222-2222-2222-222222222222', 'growth', 100, false, 1000000),
          ('33333333-3333-3333-3333-333333333333', 'enterprise', NULL, true, NULL)
        """
    )

    op.add_column("organizations", sa.Column("service_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("organizations", sa.Column("service_limit", sa.Integer(), nullable=True))
    op.add_column("organizations", sa.Column("sso_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.execute(
        """
        UPDATE organizations
        SET plan = CASE
            WHEN lower(plan) IN ('free', 'starter') THEN 'starter'
            WHEN lower(plan) IN ('pro', 'growth') THEN 'growth'
            ELSE 'enterprise'
        END
        """
    )

    op.execute(
        """
        UPDATE organizations o
        SET service_limit = p.service_limit,
            sso_enabled = p.sso_enabled
        FROM pricing_plans p
        WHERE p.name = lower(o.plan)
        """
    )

    op.execute(
        """
        UPDATE organizations o
        SET service_count = c.cnt
        FROM (
            SELECT org_id, COUNT(*)::int AS cnt
            FROM agents
            GROUP BY org_id
        ) c
        WHERE c.org_id = o.id
        """
    )

    op.create_check_constraint(
        "ck_organizations_service_count_non_negative",
        "organizations",
        "service_count >= 0",
    )
    op.create_check_constraint(
        "ck_organizations_service_limit_cap",
        "organizations",
        "service_limit IS NULL OR service_count <= service_limit",
    )

    op.create_table(
        "sso_configurations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("idp_provider", sa.String(30), nullable=False, server_default="okta"),
        sa.Column("metadata_url", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("acs_url", sa.Text(), nullable=True),
        sa.Column("x509_cert", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "sso_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("saml_name_id", sa.String(255), nullable=False, unique=True),
        sa.Column("sso_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_saml_auth", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sso_users_org_id", "sso_users", ["org_id"])
    op.create_index("ix_sso_users_user_id", "sso_users", ["user_id"])

    op.add_column("audit_logs", sa.Column("action_type", sa.String(50), nullable=True))
    op.add_column("audit_logs", sa.Column("status", sa.String(20), nullable=True))
    op.add_column("audit_logs", sa.Column("error_message", sa.Text(), nullable=True))

    op.execute(sa.text("UPDATE users SET org_id = :org_id WHERE org_id IS NULL").bindparams(org_id=DEFAULT_ORG_ID))
    op.execute(
        """
        UPDATE remediation_jobs r
        SET org_id = a.org_id
        FROM alert_records a
        WHERE r.org_id IS NULL
          AND r.alert_id = a.id
        """
    )
    op.execute(sa.text("UPDATE remediation_jobs SET org_id = :org_id WHERE org_id IS NULL").bindparams(org_id=DEFAULT_ORG_ID))
    op.execute(sa.text("UPDATE audit_logs SET org_id = :org_id WHERE org_id IS NULL").bindparams(org_id=DEFAULT_ORG_ID))

    op.alter_column("users", "org_id", existing_type=sa.String(length=36), nullable=False)
    op.alter_column("remediation_jobs", "org_id", existing_type=sa.String(length=36), nullable=False)
    op.alter_column("audit_logs", "org_id", existing_type=sa.String(length=36), nullable=False)

    for table_name in ["users", "metric_snapshots", "alert_records", "remediation_jobs", "audit_logs"]:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table_name}_org_policy ON {table_name}")
        op.execute(
            f"""
            CREATE POLICY {table_name}_org_policy
            ON {table_name}
            USING (org_id::text = current_setting('app.current_org', true))
            WITH CHECK (org_id::text = current_setting('app.current_org', true))
            """
        )


def downgrade() -> None:
    for table_name in ["audit_logs", "remediation_jobs", "alert_records", "metric_snapshots", "users"]:
        op.execute(f"DROP POLICY IF EXISTS {table_name}_org_policy ON {table_name}")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.alter_column("audit_logs", "org_id", existing_type=sa.String(length=36), nullable=True)
    op.alter_column("remediation_jobs", "org_id", existing_type=sa.String(length=36), nullable=True)
    op.alter_column("users", "org_id", existing_type=sa.String(length=36), nullable=True)

    op.drop_column("audit_logs", "error_message")
    op.drop_column("audit_logs", "status")
    op.drop_column("audit_logs", "action_type")

    op.drop_index("ix_sso_users_user_id", table_name="sso_users")
    op.drop_index("ix_sso_users_org_id", table_name="sso_users")
    op.drop_table("sso_users")
    op.drop_table("sso_configurations")

    op.drop_constraint("ck_organizations_service_limit_cap", "organizations", type_="check")
    op.drop_constraint("ck_organizations_service_count_non_negative", "organizations", type_="check")
    op.drop_column("organizations", "sso_enabled")
    op.drop_column("organizations", "service_limit")
    op.drop_column("organizations", "service_count")

    op.drop_table("pricing_plans")
