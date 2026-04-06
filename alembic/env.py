"""Alembic environment configuration for async SQLAlchemy."""

import os
import sys
from logging.config import fileConfig
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add app to path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import DATABASE_URL, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _to_sync_url(url: str) -> str:
    """Convert async SQLAlchemy URLs to sync driver URLs for Alembic."""
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg2://" + url.split("postgresql+asyncpg://", 1)[1]

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("channel_binding", None)
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=clean_query))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = DATABASE_URL
    url = _to_sync_url(url)
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = _to_sync_url(DATABASE_URL)
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
