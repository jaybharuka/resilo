# Operational Runbooks

## Overview

This document provides step-by-step procedures for common operational tasks. Use these runbooks to maintain system health, performance, and security.

## Database Maintenance

### Runbook 1: VACUUM and ANALYZE

**Purpose**: Reclaim disk space and update query statistics

**Frequency**: Weekly (off-peak hours)

**Steps**:
```bash
# Connect to database
psql -d aiops

# Run VACUUM (reclaim space)
VACUUM ANALYZE;

# Check progress
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Exit
\q
```

**Expected Output**: VACUUM completes without errors, table sizes shown

**Troubleshooting**:
- If slow: Run during maintenance window, may take 30+ minutes
- If locks: Check for long-running queries: `SELECT * FROM pg_stat_activity WHERE state = 'active';`

### Runbook 2: Index Maintenance

**Purpose**: Rebuild fragmented indexes to improve performance

**Frequency**: Monthly

**Steps**:
```bash
# Connect to database
psql -d aiops

# Find fragmented indexes
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0 OR idx_tup_read > idx_tup_fetch * 10
ORDER BY idx_tup_read DESC;

# Rebuild fragmented index
REINDEX INDEX index_name;

# Or rebuild all indexes
REINDEX DATABASE aiops;
```

**Expected Output**: Indexes rebuilt successfully

**Troubleshooting**:
- If locks: Run during maintenance window
- If slow: Check disk space first

### Runbook 3: Connection Pool Monitoring

**Purpose**: Monitor and manage database connections

**Frequency**: Daily

**Steps**:
```bash
# Check active connections
psql -d aiops -c "SELECT COUNT(*) as active_connections FROM pg_stat_activity WHERE state = 'active';"

# Check idle connections
psql -d aiops -c "SELECT COUNT(*) as idle_connections FROM pg_stat_activity WHERE state = 'idle';"

# Kill idle connections (> 1 hour)
psql -d aiops -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < NOW() - INTERVAL '1 hour';"

# Check connection limits
psql -d aiops -c "SHOW max_connections;"
```

**Expected Output**: Connection counts < 80% of max_connections

**Troubleshooting**:
- If high: Check for connection leaks in application
- If max reached: Increase max_connections and restart PostgreSQL

## Log Management

### Runbook 4: Log Rotation

**Purpose**: Rotate and compress application logs to prevent disk fill

**Frequency**: Daily (automated via logrotate)

**Manual Rotation**:
```bash
# Check current log size
du -sh /var/log/resilo/

# Rotate logs manually
sudo logrotate -f /etc/logrotate.d/resilo

# Verify rotation
ls -lh /var/log/resilo/
```

**Logrotate Configuration** (`/etc/logrotate.d/resilo`):
```
/var/log/resilo/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 resilo resilo
    sharedscripts
    postrotate
        sudo systemctl reload resilo-auth-api > /dev/null 2>&1 || true
    endscript
}
```

### Runbook 5: Log Cleanup

**Purpose**: Delete old logs to reclaim disk space

**Frequency**: Weekly

**Steps**:
```bash
# Delete logs older than 30 days
find /var/log/resilo/ -name "*.log*" -mtime +30 -delete

# Verify deletion
ls -lh /var/log/resilo/

# Check disk space
df -h /var/log/
```

**Expected Output**: Old logs deleted, disk space reclaimed

## Certificate Management

### Runbook 6: SSL Certificate Renewal

**Purpose**: Renew expiring SSL certificates

**Frequency**: Before expiration (typically 30 days before)

**Steps**:
```bash
# Check certificate expiration
openssl x509 -in /etc/ssl/certs/resilo.crt -noout -dates

# If using Let's Encrypt (certbot):
sudo certbot renew --dry-run  # Test renewal

# If renewal succeeds:
sudo certbot renew  # Actual renewal

# Verify new certificate
openssl x509 -in /etc/ssl/certs/resilo.crt -noout -dates

# Reload web server
sudo systemctl reload nginx
```

**Expected Output**: Certificate renewed, new expiration date shown

**Troubleshooting**:
- If renewal fails: Check DNS resolution, firewall rules
- If reload fails: Check nginx syntax: `sudo nginx -t`

## Scaling Procedures

### Runbook 7: Vertical Scaling (Increase Resources)

**Purpose**: Add CPU/memory to existing server

**Frequency**: As needed based on monitoring

**Steps**:
1. **Monitor current usage**:
   ```bash
   top -b -n 1 | head -20
   free -h
   df -h
   ```

2. **Plan downtime**: Schedule maintenance window

3. **Stop service**:
   ```bash
   sudo systemctl stop resilo-auth-api
   ```

4. **Increase resources** (via cloud provider or hardware):
   - Add CPU cores
   - Add RAM
   - Add disk space

5. **Verify resources**:
   ```bash
   nproc  # CPU cores
   free -h  # RAM
   df -h  # Disk
   ```

6. **Start service**:
   ```bash
   sudo systemctl start resilo-auth-api
   ```

7. **Verify health**:
   ```bash
   curl http://localhost:5001/auth/health
   ```

### Runbook 8: Horizontal Scaling (Add Servers)

**Purpose**: Add more servers behind load balancer

**Frequency**: As needed based on load

**Steps**:
1. **Deploy new server**: Follow DEPLOYMENT.md
2. **Configure load balancer**: Add new server to pool
3. **Health check**: Verify new server is healthy
4. **Monitor**: Watch for even load distribution
5. **Adjust**: Remove old servers if needed

## Performance Tuning

### Runbook 9: Query Performance Analysis

**Purpose**: Identify and optimize slow queries

**Frequency**: Monthly or when performance degrades

**Steps**:
```bash
# Enable query logging
psql -d aiops -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"  # Log queries > 1s
psql -d aiops -c "SELECT pg_reload_conf();"

# Check slow queries
psql -d aiops -c "SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Analyze slow query
EXPLAIN ANALYZE SELECT ...;

# Add index if needed
CREATE INDEX idx_name ON table(column);

# Verify improvement
EXPLAIN ANALYZE SELECT ...;
```

**Expected Output**: Query time reduced, index used in plan

### Runbook 10: Connection Pool Tuning

**Purpose**: Optimize database connection pool settings

**Frequency**: When connection issues occur

**Steps**:
```bash
# Check current settings
psql -d aiops -c "SHOW max_connections;"
psql -d aiops -c "SHOW shared_buffers;"
psql -d aiops -c "SHOW effective_cache_size;"

# Adjust for workload (requires restart)
sudo -u postgres psql -c "ALTER SYSTEM SET max_connections = 200;"
sudo -u postgres psql -c "ALTER SYSTEM SET shared_buffers = '4GB';"

# Reload configuration
sudo systemctl restart postgresql

# Verify
psql -d aiops -c "SHOW max_connections;"
```

## Security Patching

### Runbook 11: OS Security Updates

**Purpose**: Apply security patches to operating system

**Frequency**: Monthly or as critical patches released

**Steps**:
```bash
# Check available updates
sudo apt update
sudo apt list --upgradable

# Apply security updates only
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

# Or manual update
sudo apt upgrade -y

# Reboot if needed
sudo reboot

# Verify system is up
curl http://localhost:5001/auth/health
```

### Runbook 12: Python Dependency Updates

**Purpose**: Update Python packages for security fixes

**Frequency**: Monthly

**Steps**:
```bash
# Check for outdated packages
pip list --outdated

# Update specific package
pip install --upgrade package_name

# Or update all
pip install --upgrade -r requirements.txt

# Run tests
pytest tests/ -v

# Restart service
sudo systemctl restart resilo-auth-api

# Verify
curl http://localhost:5001/auth/health
```

## Monitoring Setup

### Runbook 13: Prometheus Configuration

**Purpose**: Set up Prometheus for metrics collection

**Frequency**: One-time setup, then maintenance as needed

**Steps**:
```bash
# Install Prometheus
sudo apt install -y prometheus

# Configure scrape targets (/etc/prometheus/prometheus.yml)
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'resilo-auth-api'
    static_configs:
      - targets: ['localhost:5001']
    metrics_path: '/metrics'

# Start Prometheus
sudo systemctl start prometheus
sudo systemctl enable prometheus

# Verify
curl http://localhost:9090/api/v1/targets
```

### Runbook 14: Alert Rules Configuration

**Purpose**: Set up alerting for critical metrics

**Frequency**: One-time setup, update as needed

**Steps**:
```bash
# Create alert rules (/etc/prometheus/rules.yml)
groups:
  - name: resilo
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(http_errors_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"

      - alert: HighLatency
        expr: histogram_quantile(0.95, http_request_duration_seconds) > 1.0
        for: 5m
        annotations:
          summary: "High latency detected"

# Reload Prometheus
sudo systemctl reload prometheus

# Verify rules
curl http://localhost:9090/api/v1/rules
```

## Disaster Recovery

### Runbook 15: Database Restore from Backup

**Purpose**: Restore database from backup after data loss

**Frequency**: As needed (hopefully never)

**Steps**:
```bash
# Stop application
sudo systemctl stop resilo-auth-api

# List available backups
ls -lh ./backups/

# Restore from backup
psql -d aiops < ./backups/backup_<timestamp>.sql

# Verify restore
psql -d aiops -c "SELECT COUNT(*) FROM users;"

# Start application
sudo systemctl start resilo-auth-api

# Verify
curl http://localhost:5001/auth/health
```

## Maintenance Checklist

Use this checklist for weekly/monthly maintenance:

```
WEEKLY MAINTENANCE
[ ] Check disk space (df -h)
[ ] Check database connections
[ ] Review error logs
[ ] Verify backups exist
[ ] Check monitoring alerts

MONTHLY MAINTENANCE
[ ] Run VACUUM ANALYZE
[ ] Rebuild fragmented indexes
[ ] Rotate and clean logs
[ ] Review slow queries
[ ] Update dependencies
[ ] Check certificate expiration
[ ] Review security patches

QUARTERLY MAINTENANCE
[ ] Disaster recovery drill
[ ] Performance tuning review
[ ] Capacity planning
[ ] Security audit
[ ] Documentation update
```

## Related Documentation

- `DEPLOYMENT.md`: Deployment procedures
- `INCIDENT_RESPONSE.md`: Incident response procedures
- `MONITORING.md`: Monitoring setup
- `DATA_RETENTION.md`: Data cleanup policies

## Support

For operational issues:

1. Check relevant runbook in this document
2. Check application logs
3. Check monitoring dashboard
4. Contact on-call engineer
5. Escalate to engineering manager if needed

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-31 | Initial operational runbooks |
