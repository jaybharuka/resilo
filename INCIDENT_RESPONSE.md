# Incident Response Plan

## Overview

This document defines the incident response procedures for the Resilo Auth API. It provides clear escalation paths, communication templates, and runbooks for common incidents.

## Incident Severity Levels

| Level | Name | Impact | Response Time | Example |
|-------|------|--------|----------------|---------|
| SEV1 | Critical | Service completely down, data loss risk | 15 minutes | Database corruption, all requests failing |
| SEV2 | High | Service degraded, significant impact | 30 minutes | 50% error rate, high latency (> 5s) |
| SEV3 | Medium | Service partially impacted | 2 hours | 10% error rate, slow backups |
| SEV4 | Low | Minor issues, no user impact | 24 hours | Non-critical alerts, documentation issues |

## Escalation Procedures

### SEV1 (Critical) - Immediate Action Required

1. **Declare Incident**: Post in #incidents Slack channel
   - Message: "🚨 SEV1 INCIDENT: [service] - [brief description]"
   - Include: Start time, affected services, impact estimate

2. **Notify On-Call Engineer**: 
   - Page primary on-call via PagerDuty
   - If no response in 5 minutes, page secondary on-call
   - If no response in 10 minutes, page engineering manager

3. **Establish War Room**:
   - Create Zoom call: "SEV1 Incident - [service]"
   - Post link in #incidents
   - Invite: on-call engineer, engineering manager, product manager

4. **Assign Roles**:
   - **Incident Commander**: Leads investigation, makes decisions
   - **Technical Lead**: Executes fixes
   - **Communications Lead**: Updates status page and customers

5. **Begin Investigation**: Follow relevant runbook (see below)

6. **Update Status Page**: Every 15 minutes with progress

### SEV2 (High) - Urgent Response

1. **Notify On-Call Engineer**: Page via PagerDuty
2. **Create Incident**: In incident tracking system
3. **Establish War Room**: If needed (multiple people involved)
4. **Assign Roles**: Incident commander + technical lead
5. **Update Status Page**: Every 30 minutes

### SEV3 (Medium) - Standard Response

1. **Create Incident**: In incident tracking system
2. **Assign to On-Call Engineer**: Via Slack or email
3. **Update Status Page**: If customer-facing
4. **Target Resolution**: Within 2 hours

### SEV4 (Low) - Backlog

1. **Create Ticket**: In issue tracking system
2. **Schedule for Next Sprint**: No immediate action required

## Communication Templates

### Initial Incident Notification

```
🚨 INCIDENT: [Service Name]
Severity: SEV[1-4]
Start Time: [UTC time]
Status: INVESTIGATING

Impact:
- [List affected services/users]
- [Estimated impact: X% of users affected]

Current Actions:
- [Action 1]
- [Action 2]

Updates: Every [15/30] minutes
```

### Status Update

```
📊 INCIDENT UPDATE: [Service Name]
Time: [UTC time]
Duration: [X minutes]
Status: [INVESTIGATING / MITIGATING / RESOLVED]

Progress:
- [What we've learned]
- [What we're doing now]
- [ETA for resolution]

Next Update: [Time]
```

### Resolution Notification

```
✅ INCIDENT RESOLVED: [Service Name]
Resolution Time: [X minutes]
Root Cause: [Brief description]

What happened:
[1-2 sentence summary]

What we did:
[1-2 sentence summary of fix]

Next steps:
- Post-incident review scheduled for [date/time]
- RCA will be published within 24 hours

Thank you for your patience.
```

### Post-Incident Review (RCA)

```
# Post-Incident Review: [Service Name]

## Timeline
- [HH:MM] Event occurred
- [HH:MM] Issue detected
- [HH:MM] On-call paged
- [HH:MM] Mitigation started
- [HH:MM] Service recovered

## Root Cause
[Detailed explanation of what caused the incident]

## Impact
- Duration: X minutes
- Users affected: X%
- Data loss: Yes/No

## What Went Well
- [Item 1]
- [Item 2]

## What Could Be Improved
- [Item 1]
- [Item 2]

## Action Items
- [ ] [Action] - Owner: [Name] - Due: [Date]
- [ ] [Action] - Owner: [Name] - Due: [Date]

## Lessons Learned
[Key takeaways for the team]
```

## Common Incident Runbooks

### Runbook 1: Database Connection Failures

**Symptoms**: "Failed to connect to database" errors in logs, all requests returning 500

**Diagnosis**:
```bash
# Check if database is running
psql -h localhost -U aiops -d aiops -c "SELECT 1;"

# Check connection pool
psql -d aiops -c "SELECT COUNT(*) FROM pg_stat_activity;"

# Check network connectivity
ping <database_host>
```

**Resolution**:
1. If database is down: `sudo systemctl start postgresql`
2. If connection pool exhausted: Restart application service
3. If network issue: Contact infrastructure team
4. If credentials wrong: Verify DATABASE_URL in secrets manager

**Escalation**: If not resolved in 10 minutes, page database team

### Runbook 2: High Error Rate (> 5%)

**Symptoms**: Monitoring alerts for error rate, customers reporting failures

**Diagnosis**:
```bash
# Check application logs
sudo journalctl -u resilo-auth-api -n 100 | grep ERROR

# Check error types
curl http://localhost:5001/metrics | grep http_errors_total

# Check database health
psql -d aiops -c "SELECT COUNT(*) FROM pg_stat_activity;"
```

**Resolution**:
1. Check recent deployments: `git log --oneline -5`
2. If recent deployment caused issue: Rollback
3. If database issue: Check connection pool, run VACUUM
4. If code issue: Check logs for specific error pattern

**Escalation**: If not resolved in 15 minutes, page engineering manager

### Runbook 3: High Latency (p95 > 1 second)

**Symptoms**: Slow API responses, customers reporting timeouts

**Diagnosis**:
```bash
# Check database query performance
psql -d aiops -c "SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Check CPU/memory
top -b -n 1 | head -20

# Check database locks
psql -d aiops -c "SELECT * FROM pg_locks WHERE NOT granted;"
```

**Resolution**:
1. Run ANALYZE: `psql -d aiops -c "ANALYZE;"`
2. Kill long-running queries: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE duration > 60000;`
3. Scale up resources if CPU/memory exhausted
4. Check for N+1 queries in recent code changes

**Escalation**: If not resolved in 30 minutes, page database team

### Runbook 4: Disk Space Full

**Symptoms**: "No space left on device" errors, backups failing

**Diagnosis**:
```bash
# Check disk usage
df -h /

# Find large files
du -sh /* | sort -rh | head -10

# Check backup directory
du -sh ./backups/
```

**Resolution**:
1. Delete old backups: `rm ./backups/backup_*.sql | head -n -7`
2. Clean up logs: `sudo journalctl --vacuum-time=7d`
3. If still full: Scale up disk or move data to external storage

**Escalation**: If not resolved in 15 minutes, page infrastructure team

### Runbook 5: Backup Failures

**Symptoms**: Backup health check returns "critical", no recent backups

**Diagnosis**:
```bash
# Check backup directory
ls -lh ./backups/

# Check backup logs
sudo journalctl -u resilo-auth-api | grep backup

# Check database connectivity
psql -d aiops -c "SELECT 1;"
```

**Resolution**:
1. Verify database is running: `sudo systemctl status postgresql`
2. Verify disk space: `df -h ./backups/`
3. Verify pg_dump is installed: `which pg_dump`
4. Manually create backup: `python -c "from app.core.backup import create_backup; create_backup()"`

**Escalation**: If not resolved in 30 minutes, page database team

## On-Call Rotation

### Responsibilities

**Primary On-Call Engineer**:
- Responds to all SEV1/SEV2 incidents
- Investigates issues and coordinates fixes
- Updates status page every 15 minutes
- Participates in post-incident review

**Secondary On-Call Engineer**:
- Backs up primary on-call
- Paged if primary doesn't respond within 5 minutes
- Assists with investigation and mitigation

**Engineering Manager**:
- Paged for SEV1 incidents if no response from engineers
- Escalates to VP Engineering if needed
- Ensures customer communication

### On-Call Schedule

```
Week 1: Engineer A (primary), Engineer B (secondary)
Week 2: Engineer B (primary), Engineer C (secondary)
Week 3: Engineer C (primary), Engineer A (secondary)
Week 4: Engineer A (primary), Engineer B (secondary)
```

### On-Call Expectations

- Available 24/7 during on-call week
- Respond to pages within 5 minutes
- Maintain access to production systems
- Keep phone charged and nearby
- Participate in post-incident reviews

## Post-Incident Review Process

### Timing
- SEV1: RCA within 24 hours
- SEV2: RCA within 48 hours
- SEV3: RCA within 1 week
- SEV4: Optional

### Attendees
- Incident commander
- Technical lead
- Engineering manager
- Product manager (if customer-facing)

### Agenda
1. Timeline review (5 min)
2. Root cause analysis (15 min)
3. Impact assessment (5 min)
4. What went well (5 min)
5. What could improve (10 min)
6. Action items (10 min)

### Output
- RCA document published within 24 hours
- Action items tracked and assigned
- Lessons learned shared with team
- Process improvements implemented

## Incident Tracking

### Required Information
- Incident ID: Auto-generated
- Service: Which service was affected
- Severity: SEV1-4
- Start time: When issue was detected
- End time: When service recovered
- Root cause: What caused the issue
- Impact: How many users/requests affected
- Resolution: What was done to fix it

### Tracking System
- **Tool**: Jira / Linear / GitHub Issues
- **Label**: `incident`
- **Status**: `open` → `in-progress` → `resolved` → `closed`

## Escalation Contacts

| Role | Name | Phone | Email | Slack |
|------|------|-------|-------|-------|
| VP Engineering | [Name] | [Phone] | [Email] | @[handle] |
| Engineering Manager | [Name] | [Phone] | [Email] | @[handle] |
| Database Team Lead | [Name] | [Phone] | [Email] | @[handle] |
| Infrastructure Lead | [Name] | [Phone] | [Email] | @[handle] |

## Related Documentation

- `DEPLOYMENT.md`: Deployment procedures
- `TROUBLESHOOTING.md`: Common issues and solutions
- `MONITORING.md`: Monitoring and alerting setup
- `RUNBOOKS.md`: Detailed runbooks for all services

## Incident Response Checklist

Use this checklist during incidents:

```
INCIDENT RESPONSE CHECKLIST

[ ] Declare incident in #incidents
[ ] Page on-call engineer
[ ] Establish war room (if SEV1/2)
[ ] Assign incident commander
[ ] Assign technical lead
[ ] Assign communications lead
[ ] Begin investigation
[ ] Update status page (initial)
[ ] Update status page (every 15 min)
[ ] Implement mitigation
[ ] Verify fix
[ ] Declare resolution
[ ] Update status page (final)
[ ] Schedule post-incident review
[ ] Document RCA
[ ] Track action items
[ ] Close incident
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-31 | Initial incident response plan |
