"""
sqlite_migrator.py — Lightweight SQLite schema migration runner.

Each caller passes:
  - db_path: path to the SQLite database file
  - migrations_dir: directory containing N_description.sql files

Applied migrations are tracked in _schema_migrations table inside the DB.
Migrations are applied atomically: each .sql file runs inside an explicit
BEGIN/COMMIT; a failure rolls back that file and raises so the caller fails
fast with a clear message.
"""
from __future__ import annotations

import logging
import os
import pathlib
import sqlite3

log = logging.getLogger(__name__)


def run_sqlite_migrations(db_path: str, migrations_dir: str) -> None:
    """Apply any unapplied .sql migration files from migrations_dir to db_path."""
    # ── Input validation & canonicalization ──────────────────────────────────
    db_path = str(pathlib.Path(db_path).resolve())

    migrations_path = pathlib.Path(migrations_dir).resolve()
    if not migrations_path.exists():
        raise RuntimeError(
            f"SQLite migrations directory not found: {migrations_dir!r}\n"
            "Ensure the migrations/sqlite/ tree is present in the deployment."
        )
    if not migrations_path.is_dir():
        raise RuntimeError(
            f"SQLite migrations path is not a directory: {migrations_dir!r}"
        )
    migrations_dir = str(migrations_path)

    # ── Apply migrations ──────────────────────────────────────────────────────
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        sql_files = sorted(
            f for f in os.listdir(migrations_dir)
            if f.endswith(".sql")
        )

        for filename in sql_files:
            # Guard: migration filename must not escape the migrations directory.
            filepath = (migrations_path / filename).resolve()
            if not str(filepath).startswith(migrations_dir + os.sep):
                raise RuntimeError(
                    f"Migration filename escapes migrations directory: {filename!r}"
                )

            row = conn.execute(
                "SELECT 1 FROM _schema_migrations WHERE filename = ?", (filename,)
            ).fetchone()
            if row:
                continue

            with open(filepath, encoding="utf-8") as fh:
                sql = fh.read()

            # Execute each DDL statement individually inside an explicit
            # transaction so a failure is fully rolled back — executescript()
            # issues an implicit COMMIT before running and cannot be rolled back.
            try:
                statements = [s.strip() for s in sql.split(";") if s.strip()]
                conn.execute("BEGIN")
                for stmt in statements:
                    conn.execute(stmt)
                conn.execute(
                    "INSERT INTO _schema_migrations (filename) VALUES (?)", (filename,)
                )
                conn.execute("COMMIT")
                log.info("Applied SQLite migration: %s → %s", filename, db_path)
            except Exception as exc:
                conn.execute("ROLLBACK")
                log.error("Failed to apply SQLite migration %s: %s", filename, exc)
                raise

    finally:
        conn.close()
