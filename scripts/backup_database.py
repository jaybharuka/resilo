#!/usr/bin/env python3
"""
Database backup script for PostgreSQL.
Backs up the entire database to a timestamped file with compression.
Supports retention policy (delete backups older than N days).

Usage:
    python scripts/backup_database.py
    
Environment variables:
    DATABASE_URL         PostgreSQL connection string (required)
    BACKUP_DIR          Directory to store backups (default: ./backups)
    BACKUP_RETENTION_DAYS  Delete backups older than this many days (default: 30)
"""

import os
import sys
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("backup")


def parse_db_url(url: str) -> dict:
    """Parse PostgreSQL connection URL into components."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "database": parsed.path.lstrip("/") or "postgres",
    }


def backup_database() -> bool:
    """
    Create a backup of the PostgreSQL database using pg_dump.
    Returns True on success, False on failure.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL environment variable not set")
        return False

    backup_dir = os.getenv("BACKUP_DIR", "./backups")
    Path(backup_dir).mkdir(parents=True, exist_ok=True)

    db_config = parse_db_url(db_url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"backup_{db_config['database']}_{timestamp}.sql.gz")

    log.info(f"Starting backup of database '{db_config['database']}' to {backup_file}")

    try:
        # Build pg_dump command with compression
        env = os.environ.copy()
        if db_config["password"]:
            env["PGPASSWORD"] = db_config["password"]

        cmd = [
            "pg_dump",
            "-h", db_config["host"],
            "-p", str(db_config["port"]),
            "-U", db_config["user"],
            "-d", db_config["database"],
            "-v",  # verbose
            "-Fc",  # custom format (compressed)
        ]

        with open(backup_file, "wb") as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                env=env,
            )
            _, stderr = process.communicate()

        if process.returncode != 0:
            log.error(f"pg_dump failed: {stderr.decode()}")
            if os.path.exists(backup_file):
                os.remove(backup_file)
            return False

        file_size = os.path.getsize(backup_file) / (1024 * 1024)  # MB
        log.info(f"Backup completed successfully: {backup_file} ({file_size:.2f} MB)")
        return True

    except FileNotFoundError:
        log.error("pg_dump not found. Install PostgreSQL client tools.")
        return False
    except Exception as e:
        log.error(f"Backup failed: {e}")
        return False


def cleanup_old_backups() -> None:
    """Delete backups older than BACKUP_RETENTION_DAYS."""
    backup_dir = os.getenv("BACKUP_DIR", "./backups")
    retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

    if not os.path.exists(backup_dir):
        return

    cutoff_time = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0

    for filename in os.listdir(backup_dir):
        if not filename.startswith("backup_") or not filename.endswith(".sql.gz"):
            continue

        filepath = os.path.join(backup_dir, filename)
        file_time = datetime.fromtimestamp(os.path.getmtime(filepath))

        if file_time < cutoff_time:
            try:
                os.remove(filepath)
                log.info(f"Deleted old backup: {filename}")
                deleted_count += 1
            except Exception as e:
                log.error(f"Failed to delete {filename}: {e}")

    if deleted_count > 0:
        log.info(f"Cleanup complete: deleted {deleted_count} old backup(s)")


def main():
    """Run backup and cleanup."""
    success = backup_database()
    cleanup_old_backups()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
