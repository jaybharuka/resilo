"""
Database backup and recovery helpers.

Implements automated backups using pg_dump for disaster recovery.
Backups are stored locally with retention policy.
"""

import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("backup")


def get_backup_dir() -> Path:
    """Get backup directory from environment or use default."""
    backup_dir = os.getenv("BACKUP_DIR", "./backups")
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path


def get_database_url() -> str:
    """Get database URL from environment."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable not set")
    return url


def parse_database_url(url: str) -> dict:
    """
    Parse PostgreSQL connection URL.
    
    Format: postgresql+asyncpg://user:password@host:port/database
    Returns: {host, port, user, password, database}
    """
    from urllib.parse import urlparse

    # Remove the asyncpg driver part
    clean_url = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(clean_url)
    
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "database": parsed.path.lstrip("/") or "postgres",
    }


def create_backup(backup_dir: Optional[Path] = None) -> str:
    """
    Create a database backup using pg_dump.
    
    Args:
        backup_dir: Directory to store backup (uses BACKUP_DIR env var if not provided)
    
    Returns:
        Path to created backup file
    
    Raises:
        RuntimeError: If backup fails
    """
    if backup_dir is None:
        backup_dir = get_backup_dir()
    
    db_url = get_database_url()
    db_config = parse_database_url(db_url)
    
    # Create backup filename with timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"backup_{timestamp}.sql"
    
    try:
        # Build pg_dump command
        env = os.environ.copy()
        if db_config["password"]:
            env["PGPASSWORD"] = db_config["password"]
        
        cmd = [
            "pg_dump",
            "-h", db_config["host"],
            "-p", str(db_config["port"]),
            "-U", db_config["user"],
            "-d", db_config["database"],
            "-F", "p",  # Plain text format
            "-v",  # Verbose
        ]
        
        with open(backup_file, "w") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                env=env,
                timeout=300,  # 5 minute timeout
            )
        
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr.decode()}")
        
        file_size = backup_file.stat().st_size
        log.info(f"Backup created: {backup_file} ({file_size} bytes)")
        
        return str(backup_file)
    
    except subprocess.TimeoutExpired:
        raise RuntimeError("Backup timeout (5 minutes exceeded)")
    except Exception as e:
        log.error(f"Backup failed: {e}")
        raise


def cleanup_old_backups(backup_dir: Optional[Path] = None, keep_count: int = 7) -> int:
    """
    Delete old backups, keeping only the most recent N.
    
    Args:
        backup_dir: Directory containing backups (uses BACKUP_DIR env var if not provided)
        keep_count: Number of recent backups to keep (default 7)
    
    Returns:
        Number of backups deleted
    """
    if backup_dir is None:
        backup_dir = get_backup_dir()
    
    # Get all backup files sorted by modification time (newest first)
    backup_files = sorted(
        backup_dir.glob("backup_*.sql"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    
    # Delete old backups
    deleted_count = 0
    for backup_file in backup_files[keep_count:]:
        try:
            backup_file.unlink()
            log.info(f"Deleted old backup: {backup_file}")
            deleted_count += 1
        except Exception as e:
            log.error(f"Failed to delete backup {backup_file}: {e}")
    
    if deleted_count > 0:
        log.info(f"Cleanup removed {deleted_count} old backups (kept {keep_count})")
    
    return deleted_count


def get_recent_backups(backup_dir: Optional[Path] = None, limit: int = 10) -> List[dict]:
    """
    Get list of recent backups with metadata.
    
    Args:
        backup_dir: Directory containing backups (uses BACKUP_DIR env var if not provided)
        limit: Maximum number of backups to return
    
    Returns:
        List of dicts with backup metadata: {path, size, created_at}
    """
    if backup_dir is None:
        backup_dir = get_backup_dir()
    
    backups = []
    for backup_file in sorted(
        backup_dir.glob("backup_*.sql"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )[:limit]:
        stat = backup_file.stat()
        backups.append({
            "path": str(backup_file),
            "filename": backup_file.name,
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    
    return backups


def verify_backup(backup_file: str) -> bool:
    """
    Verify backup integrity by checking if it's a valid SQL file.
    
    Args:
        backup_file: Path to backup file
    
    Returns:
        True if backup appears valid
    """
    try:
        backup_path = Path(backup_file)
        
        if not backup_path.exists():
            log.error(f"Backup file not found: {backup_file}")
            return False
        
        if backup_path.stat().st_size == 0:
            log.error(f"Backup file is empty: {backup_file}")
            return False
        
        # Check if file starts with SQL comment or CREATE statement
        with open(backup_path, "r") as f:
            first_line = f.readline()
            if not (first_line.startswith("--") or first_line.startswith("CREATE")):
                log.error(f"Backup file doesn't appear to be valid SQL: {backup_file}")
                return False
        
        log.info(f"Backup verified: {backup_file}")
        return True
    
    except Exception as e:
        log.error(f"Backup verification failed: {e}")
        return False


async def create_backup_async(backup_dir: Optional[Path] = None) -> str:
    """
    Create backup asynchronously (wrapper for async context).
    
    Args:
        backup_dir: Directory to store backup
    
    Returns:
        Path to created backup file
    """
    return create_backup(backup_dir)
