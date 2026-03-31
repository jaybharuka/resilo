# Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the Resilo Auth API to production. Follow all steps carefully to ensure a successful, safe deployment.

## Pre-Deployment Checklist

Before deploying, verify all of the following:

### Secrets & Configuration
- [ ] All required environment variables are set (JWT_SECRET_KEY, ENCRYPTION_KEY, DATABASE_URL)
- [ ] ENCRYPTION_KEY is a valid Fernet key (not from previous environment)
- [ ] DATABASE_URL points to correct database (not production data on staging)
- [ ] ENVIRONMENT is set to "production" (enforces HTTPS)
- [ ] ADMIN_DEFAULT_PASSWORD is set to a strong, unique password
- [ ] All secrets are stored in secrets manager (not in .env file)

### Code & Testing
- [ ] All tests pass locally: `pytest tests/ -v`
- [ ] Code review completed and approved
- [ ] No uncommitted changes: `git status` shows clean working directory
- [ ] Latest code is pushed to main branch: `git log --oneline -5`
- [ ] No breaking changes to database schema (or migration plan exists)

### Database
- [ ] Database backup exists and is recent (< 24 hours old)
- [ ] Backup has been tested (restore verified in test environment)
- [ ] Database migrations are up to date: `alembic current`
- [ ] Sufficient disk space available (check with `df -h`)

### Monitoring & Alerting
- [ ] Monitoring dashboards are configured
- [ ] Alert rules are configured and tested
- [ ] On-call rotation is active
- [ ] Incident response plan is documented

### Documentation
- [ ] Deployment notes are written (what changed, why, risks)
- [ ] Rollback plan is documented
- [ ] Team is notified of deployment window

## Deployment Steps

### 1. Pre-Deployment Backup

Create a backup before deploying:

```bash
# SSH to production server
ssh deploy@prod.example.com

# Create backup
python -c "
from app.core.backup import create_backup
backup_file = create_backup()
print(f'Backup created: {backup_file}')
"

# Verify backup
ls -lh ./backups/ | head -1
```

### 2. Pull Latest Code

```bash
cd /opt/resilo
git fetch origin
git checkout main
git log --oneline -1  # Verify correct commit
```

### 3. Install Dependencies

```bash
# Create/activate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Run Database Migrations

```bash
# Run Alembic migrations
alembic upgrade head

# Verify migrations
alembic current
```

### 5. Run Tests

```bash
# Run test suite
pytest tests/ -v --tb=short

# If tests fail, STOP and investigate before proceeding
```

### 6. Stop Current Service

```bash
# Stop the running service
sudo systemctl stop resilo-auth-api

# Verify it's stopped
sudo systemctl status resilo-auth-api
```

### 7. Deploy New Code

```bash
# Copy new code to deployment directory
cp -r app/ /opt/resilo/app/
cp requirements.txt /opt/resilo/

# Verify files are in place
ls -la /opt/resilo/app/api/auth_api.py
```

### 8. Start Service

```bash
# Start the service
sudo systemctl start resilo-auth-api

# Verify it started
sudo systemctl status resilo-auth-api

# Check logs for errors
sudo journalctl -u resilo-auth-api -n 50 -f
```

## Post-Deployment Verification

### 1. Health Checks

```bash
# Check API health
curl -s http://localhost:5001/auth/health | jq .
# Expected: {"status":"ok","service":"auth-api","version":"2.0.0"}

# Check backup health
curl -s http://localhost:5001/auth/health/backups | jq .
# Expected: {"status":"ok",...}

# Check metrics endpoint
curl -s http://localhost:5001/metrics | head -20
# Should show Prometheus metrics
```

### 2. Smoke Tests

```bash
# Test login endpoint
curl -X POST http://localhost:5001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<admin_password>"}' \
  | jq .

# Test user creation (requires valid token)
curl -X POST http://localhost:5001/users \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","username":"testuser","password":"TestPassword123!","role":"employee"}' \
  | jq .
```

### 3. Log Monitoring

```bash
# Monitor logs for errors
sudo journalctl -u resilo-auth-api -f

# Check for startup errors
sudo journalctl -u resilo-auth-api -n 100 | grep -i error

# Verify secrets validation passed
sudo journalctl -u resilo-auth-api -n 100 | grep "secrets validated"
```

### 4. Database Verification

```bash
# Connect to database
psql -d aiops -c "SELECT COUNT(*) FROM users;"

# Check recent audit logs
psql -d aiops -c "SELECT action, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 5;"
```

### 5. Monitoring Dashboard

- [ ] Check Prometheus dashboard for metrics
- [ ] Verify request latency is normal (< 500ms p95)
- [ ] Verify error rate is low (< 1%)
- [ ] Check database connection pool health

## Rollback Procedures

If deployment fails or causes issues, follow these steps:

### Immediate Rollback (< 5 minutes after deployment)

```bash
# Stop the service
sudo systemctl stop resilo-auth-api

# Revert to previous code
cd /opt/resilo
git checkout HEAD~1  # Go back one commit

# Reinstall dependencies (if needed)
pip install -r requirements.txt

# Start service
sudo systemctl start resilo-auth-api

# Verify it's working
curl http://localhost:5001/auth/health
```

### Database Rollback (if migrations caused issues)

```bash
# Revert to previous migration
alembic downgrade -1

# Verify current migration
alembic current

# Restore from backup if needed
psql -d aiops < ./backups/backup_<timestamp>.sql
```

### Full Rollback (if data corruption occurred)

```bash
# Stop service
sudo systemctl stop resilo-auth-api

# Restore database from backup
psql -d aiops < ./backups/backup_<timestamp>.sql

# Revert code to previous version
git checkout <previous_commit_hash>

# Reinstall dependencies
pip install -r requirements.txt

# Start service
sudo systemctl start resilo-auth-api

# Verify
curl http://localhost:5001/auth/health
```

## Monitoring & Alerting

### Key Metrics to Monitor

- **Request Latency**: p50, p95, p99 (should be < 500ms, < 1s, < 2s)
- **Error Rate**: 5xx errors (should be < 1%)
- **Database Connections**: Active connections (should be < max_connections / 2)
- **Backup Age**: Latest backup (should be < 24 hours)
- **Disk Space**: Available space (should be > 20% free)

### Alert Rules

Set up alerts for:

```
- http_requests_total{status_code=~"5.."}  > 10 in 5m  (5xx errors)
- http_request_duration_seconds{quantile="0.95"} > 1.0  (high latency)
- backup_age_hours > 24  (stale backups)
- disk_free_percent < 20  (low disk space)
- database_connections > max_connections * 0.8  (connection pool exhaustion)
```

### Logging

Monitor application logs for:

```bash
# Errors
sudo journalctl -u resilo-auth-api | grep ERROR

# Warnings
sudo journalctl -u resilo-auth-api | grep WARNING

# Startup events
sudo journalctl -u resilo-auth-api | grep "startup\|migration\|backup"
```

## Troubleshooting

### Service Won't Start

**Symptom**: `systemctl start resilo-auth-api` fails

**Diagnosis**:
```bash
# Check logs
sudo journalctl -u resilo-auth-api -n 50

# Check if port is in use
sudo lsof -i :5001

# Check file permissions
ls -la /opt/resilo/app/
```

**Solutions**:
- Missing environment variables: Set all required secrets
- Port in use: Kill process using port or change port
- Permission denied: Fix file ownership: `sudo chown -R deploy:deploy /opt/resilo`

### Database Connection Fails

**Symptom**: "Failed to connect to database" in logs

**Diagnosis**:
```bash
# Test database connection
psql -h localhost -U aiops -d aiops -c "SELECT 1;"

# Check DATABASE_URL
echo $DATABASE_URL
```

**Solutions**:
- Wrong password: Verify DATABASE_URL in secrets manager
- Database not running: `sudo systemctl start postgresql`
- Network issue: Check firewall rules, DNS resolution

### High Error Rate After Deployment

**Symptom**: 5xx errors in logs or monitoring dashboard

**Diagnosis**:
```bash
# Check recent errors
sudo journalctl -u resilo-auth-api -n 100 | grep ERROR

# Check database
psql -d aiops -c "SELECT COUNT(*) FROM users;"

# Check disk space
df -h /
```

**Solutions**:
- Schema mismatch: Run migrations: `alembic upgrade head`
- Disk full: Clean up old backups or logs
- Database issue: Restore from backup
- Code bug: Rollback to previous version

### Slow Requests After Deployment

**Symptom**: Request latency increased significantly

**Diagnosis**:
```bash
# Check database query performance
psql -d aiops -c "SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Check database connections
psql -d aiops -c "SELECT COUNT(*) FROM pg_stat_activity;"

# Check CPU/memory
top -b -n 1 | head -20
```

**Solutions**:
- Database slow: Run ANALYZE: `psql -d aiops -c "ANALYZE;"`
- Too many connections: Increase connection pool or reduce load
- Resource exhaustion: Scale up server or optimize queries

## Deployment Checklist Template

Use this checklist for each deployment:

```
Deployment: Issue #<number> - <description>
Date: YYYY-MM-DD HH:MM UTC
Deployed by: <name>

PRE-DEPLOYMENT
[ ] Secrets verified
[ ] Tests passing
[ ] Code reviewed
[ ] Backup created and tested
[ ] Migrations planned
[ ] Team notified

DEPLOYMENT
[ ] Code pulled
[ ] Dependencies installed
[ ] Migrations run
[ ] Tests passed
[ ] Service stopped
[ ] Code deployed
[ ] Service started

POST-DEPLOYMENT
[ ] Health checks pass
[ ] Smoke tests pass
[ ] Logs clean
[ ] Database verified
[ ] Monitoring active
[ ] No alerts firing

SIGN-OFF
Deployed: ✓
Status: OK / ISSUES
Issues: <list any issues>
Rollback needed: Yes / No
```

## Related Documentation

- `SECRETS_MANAGEMENT.md`: How to manage secrets
- `DATA_RETENTION.md`: Data cleanup policies
- `DATA_RETENTION.md`: Backup strategy
- `.env.example`: Environment variable template
- `requirements.txt`: Python dependencies

## Support

For deployment issues:

1. Check this guide's troubleshooting section
2. Check application logs: `sudo journalctl -u resilo-auth-api -f`
3. Check monitoring dashboard
4. Contact on-call engineer
5. If critical: Execute rollback procedure

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-31 | Initial deployment guide |
