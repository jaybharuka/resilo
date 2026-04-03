"""
Data retention policies and cleanup helpers.

Implements automatic cleanup of expired data to comply with GDPR and other regulations.
Policies:
- User sessions: 30 days
- Password reset tokens: 24 hours
- Invite tokens: based on TTL (default 72 hours)
- Audit logs: 90 days
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import logging

log = logging.getLogger("retention")


# Retention periods (in days)
RETENTION_POLICIES = {
    "user_sessions": 30,          # Delete sessions older than 30 days
    "password_reset_tokens": 1,   # Delete tokens older than 24 hours
    "invite_tokens": 3,           # Delete invites older than 3 days (default TTL)
    "audit_logs": 90,             # Delete audit logs older than 90 days
}


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """
    Delete expired user sessions (older than RETENTION_POLICIES['user_sessions'] days).
    
    Args:
        db: AsyncSession for database access
    
    Returns:
        Number of sessions deleted
    """
    from database import UserSession
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_POLICIES["user_sessions"])
    
    result = await db.execute(
        delete(UserSession).where(UserSession.created_at < cutoff_date)
    )
    await db.commit()
    
    deleted_count = result.rowcount
    if deleted_count > 0:
        log.info(f"Deleted {deleted_count} expired user sessions (older than {RETENTION_POLICIES['user_sessions']} days)")
    
    return deleted_count


async def cleanup_expired_password_reset_tokens(db: AsyncSession) -> int:
    """
    Delete expired password reset tokens (older than RETENTION_POLICIES['password_reset_tokens'] days).
    
    Args:
        db: AsyncSession for database access
    
    Returns:
        Number of tokens deleted
    """
    from database import PasswordResetToken
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_POLICIES["password_reset_tokens"])
    
    result = await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.created_at < cutoff_date)
    )
    await db.commit()
    
    deleted_count = result.rowcount
    if deleted_count > 0:
        log.info(f"Deleted {deleted_count} expired password reset tokens (older than {RETENTION_POLICIES['password_reset_tokens']} days)")
    
    return deleted_count


async def cleanup_expired_invites(db: AsyncSession) -> int:
    """
    Delete expired invite tokens (past their expiration date).
    
    Args:
        db: AsyncSession for database access
    
    Returns:
        Number of invites deleted
    """
    from database import InviteToken
    
    now = datetime.now(timezone.utc)
    
    result = await db.execute(
        delete(InviteToken).where(InviteToken.expires_at < now)
    )
    await db.commit()
    
    deleted_count = result.rowcount
    if deleted_count > 0:
        log.info(f"Deleted {deleted_count} expired invite tokens")
    
    return deleted_count


async def cleanup_old_audit_logs(db: AsyncSession) -> int:
    """
    Delete old audit logs (older than RETENTION_POLICIES['audit_logs'] days).
    
    Args:
        db: AsyncSession for database access
    
    Returns:
        Number of audit logs deleted
    """
    from database import AuditLog
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_POLICIES["audit_logs"])
    
    result = await db.execute(
        delete(AuditLog).where(AuditLog.created_at < cutoff_date)
    )
    await db.commit()
    
    deleted_count = result.rowcount
    if deleted_count > 0:
        log.info(f"Deleted {deleted_count} old audit logs (older than {RETENTION_POLICIES['audit_logs']} days)")
    
    return deleted_count


async def cleanup_all_expired_data(db: AsyncSession) -> dict:
    """
    Run all cleanup operations.
    
    Args:
        db: AsyncSession for database access
    
    Returns:
        Dictionary with cleanup results for each data type
    """
    log.info("Starting data retention cleanup...")
    
    results = {
        "sessions": await cleanup_expired_sessions(db),
        "password_reset_tokens": await cleanup_expired_password_reset_tokens(db),
        "invites": await cleanup_expired_invites(db),
        "audit_logs": await cleanup_old_audit_logs(db),
    }
    
    total_deleted = sum(results.values())
    log.info(f"Data retention cleanup completed. Total records deleted: {total_deleted}")
    
    return results
