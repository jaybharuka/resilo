# Data Retention Policy

## Overview

This document describes the data retention policies for the Resilo project. Automatic cleanup runs on application startup and should be scheduled to run daily via cron or similar scheduler.

## Retention Periods

| Data Type | Retention Period | Reason | Compliance |
|-----------|------------------|--------|-----------|
| User Sessions | 30 days | Prevent stale sessions from accumulating | GDPR, PCI-DSS |
| Password Reset Tokens | 24 hours | Security: tokens expire quickly | OWASP |
| Invite Tokens | 3 days (default TTL) | Prevent old invites from being used | Security |
| Audit Logs | 90 days | Maintain compliance audit trail | SOC 2, HIPAA |

## Cleanup Operations

### User Sessions
- **Policy**: Delete sessions older than 30 days
- **Trigger**: Automatic on startup, should run daily
- **Impact**: Users with inactive sessions > 30 days will need to log in again
- **Data**: `user_sessions` table

### Password Reset Tokens
- **Policy**: Delete tokens older than 24 hours
- **Trigger**: Automatic on startup, should run daily
- **Impact**: Users cannot use password reset links older than 24 hours
- **Data**: `password_reset_tokens` table

### Invite Tokens
- **Policy**: Delete tokens past their expiration date
- **Trigger**: Automatic on startup, should run daily
- **Impact**: Expired invites cannot be accepted
- **Data**: `invite_tokens` table

### Audit Logs
- **Policy**: Delete logs older than 90 days
- **Trigger**: Automatic on startup, should run daily
- **Impact**: Audit trail retained for 90 days (meets most compliance requirements)
- **Data**: `audit_logs` table

## Implementation

### Automatic Cleanup

Cleanup runs automatically on application startup:

```python
# In app/api/auth_api.py @app.on_event("startup")
async with SessionLocal() as db:
    await cleanup_all_expired_data(db)
```

### Manual Cleanup

To run cleanup manually:

```python
from app.core.retention import cleanup_all_expired_data
from app.core.database import SessionLocal

async with SessionLocal() as db:
    results = await cleanup_all_expired_data(db)
    print(results)
    # Output: {'sessions': 42, 'password_reset_tokens': 15, 'invites': 3, 'audit_logs': 128}
```

### Scheduled Cleanup (Cron)

For production, schedule daily cleanup via cron:

```bash
# Run cleanup daily at 2 AM
0 2 * * * /usr/bin/python /path/to/cleanup_task.py
```

Example cleanup script (`cleanup_task.py`):

```python
#!/usr/bin/env python
import asyncio
from app.core.database import SessionLocal
from app.core.retention import cleanup_all_expired_data

async def main():
    async with SessionLocal() as db:
        results = await cleanup_all_expired_data(db)
        print(f"Cleanup completed: {results}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Compliance

### GDPR (General Data Protection Regulation)
- **Right to be Forgotten**: Audit logs deleted after 90 days
- **Data Minimization**: Expired sessions and tokens automatically removed
- **Retention Limits**: No data retained longer than necessary

### HIPAA (Health Insurance Portability and Accountability Act)
- **Audit Controls**: Audit logs retained for 90 days
- **Access Controls**: Sessions expire after 30 days of inactivity
- **Data Integrity**: Cleanup prevents unauthorized access to old tokens

### PCI-DSS (Payment Card Industry Data Security Standard)
- **Requirement 3.2.1**: Render PAN unreadable (sessions expire)
- **Requirement 10.7**: Retain audit logs for at least 1 year (90 days minimum)
- **Requirement 8.1.4**: Remove/disable inactive user accounts (sessions cleanup)

### SOC 2 Type II
- **Availability**: Cleanup prevents database bloat and performance degradation
- **Confidentiality**: Expired tokens cannot be reused
- **Integrity**: Audit logs maintained for investigation

## Monitoring

### Cleanup Logs

Monitor cleanup operations in application logs:

```bash
# View cleanup logs
grep "Data retention cleanup" /var/log/resilo/auth_api.log

# Example output:
# 2026-03-31 02:00:00 INFO retention: Starting data retention cleanup...
# 2026-03-31 02:00:01 INFO retention: Deleted 42 expired user sessions (older than 30 days)
# 2026-03-31 02:00:01 INFO retention: Deleted 15 expired password reset tokens (older than 1 days)
# 2026-03-31 02:00:02 INFO retention: Deleted 3 expired invite tokens
# 2026-03-31 02:00:05 INFO retention: Deleted 128 old audit logs (older than 90 days)
# 2026-03-31 02:00:05 INFO retention: Data retention cleanup completed. Total records deleted: 188
```

### Database Size

Monitor database growth to ensure cleanup is working:

```sql
-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check audit_logs table specifically
SELECT 
    COUNT(*) as total_records,
    COUNT(CASE WHEN created_at > NOW() - INTERVAL '90 days' THEN 1 END) as retained_records,
    COUNT(CASE WHEN created_at <= NOW() - INTERVAL '90 days' THEN 1 END) as should_be_deleted
FROM audit_logs;
```

## Customization

### Changing Retention Periods

Edit `app/core/retention.py`:

```python
RETENTION_POLICIES = {
    "user_sessions": 30,          # Change to desired days
    "password_reset_tokens": 1,   # Change to desired days
    "invite_tokens": 3,           # Change to desired days
    "audit_logs": 90,             # Change to desired days
}
```

### Adding New Cleanup Operations

1. Create cleanup function in `app/core/retention.py`:

```python
async def cleanup_custom_data(db: AsyncSession) -> int:
    """Delete custom data based on retention policy."""
    from database import CustomTable
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_POLICIES["custom"])
    result = await db.execute(
        delete(CustomTable).where(CustomTable.created_at < cutoff_date)
    )
    await db.commit()
    return result.rowcount
```

2. Add to `cleanup_all_expired_data()`:

```python
results = {
    "sessions": await cleanup_expired_sessions(db),
    "password_reset_tokens": await cleanup_expired_password_reset_tokens(db),
    "invites": await cleanup_expired_invites(db),
    "audit_logs": await cleanup_old_audit_logs(db),
    "custom": await cleanup_custom_data(db),  # Add new cleanup
}
```

## Troubleshooting

### Cleanup Not Running

**Problem**: Cleanup logs don't appear on startup.

**Solution**:
1. Check application logs for errors
2. Verify database connection is working
3. Ensure cleanup functions are imported correctly
4. Check database permissions (need DELETE privilege)

### Database Still Growing

**Problem**: Database size continues to grow despite cleanup.

**Solution**:
1. Check if cleanup is actually running (look for logs)
2. Verify retention periods are appropriate
3. Check for other tables accumulating data
4. Consider running VACUUM to reclaim space:
   ```sql
   VACUUM ANALYZE;
   ```

### Cleanup Deletes Too Much Data

**Problem**: Cleanup is deleting data you wanted to keep.

**Solution**:
1. Increase retention periods in `RETENTION_POLICIES`
2. Disable cleanup for specific tables temporarily
3. Restore from backup if needed
4. Document the change and notify compliance team

## Related Files

- `app/core/retention.py`: Cleanup implementation
- `app/api/auth_api.py`: Startup integration
- `SECRETS_MANAGEMENT.md`: Related to data protection
- `DATA_PROTECTION.md`: Encryption and security

## Security Checklist

- [ ] Cleanup runs automatically on startup
- [ ] Cleanup is scheduled to run daily
- [ ] Cleanup logs are monitored
- [ ] Database size is monitored
- [ ] Retention periods meet compliance requirements
- [ ] Backups are taken before cleanup (optional but recommended)
- [ ] Cleanup is tested in staging before production
- [ ] Retention policy is documented and reviewed annually
