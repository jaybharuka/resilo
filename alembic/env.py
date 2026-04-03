"""Alembic environment — uses DATABASE_URL from the environment."""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Ensure project root is on the path so app.core.database resolves ─────────
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── Alembic Config object ─────────────────────────────────────────────────────
config = context.config

# ── DATABASE_URL — required; asyncpg driver replaced with psycopg2 for Alembic ─
_raw_url = os.getenv("DATABASE_URL")
if not _raw_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is required for Alembic migrations.\n"
        "Set it in your .env file or export it before running alembic commands.\n"
        "Example: DATABASE_URL=postgresql+asyncpg://aiops:pass@localhost:5432/aiops"
    )
_db_url = _raw_url.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import the SQLAlchemy metadata from the application models ────────────────
from app.core.database import Base  # noqa: E402 — path must be set up first
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
