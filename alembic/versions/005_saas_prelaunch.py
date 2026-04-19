"""SaaS prelaunch migrations (stub — already applied to DB).

Revision ID: 005
Revises: 004
Create Date: 2026-04-10

"""
from typing import Sequence, Union

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
