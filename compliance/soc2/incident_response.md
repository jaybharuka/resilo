# SOC2 Type I — Incident Response Evidence

**Control Domain:** Incident Response and Communication
**Last Reviewed:** 2026-04-07
**Owner:** Engineering / Security Team
**Status:** Implemented

---

## CC9.6 — Incident Response Procedures

**Requirement:** The entity has formal procedures for responding to security incidents.

**Incident Severity Levels:**

| Level | Definition | Response SLA |
|---|---|---|
| P0 — Critical | Data breach, RLS bypass, auth bypass | 15 minutes |
| P1 — High | Service outage, failed health probes | 1 hour |
| P2 — Medium | Elevated error rates, degraded performance | 4 hours |
| P3 — Low | Non-critical alert, cosmetic issue | 24 hours |

---

## Incident Response Runbook

### Step 1 — Detection

Incidents are detected via:
- Prometheus alert firing (Alertmanager → Slack `#incidents`)
- Kubernetes liveness/readiness probe failure (pod restart + PagerDuty alert)
- Manual report from customer or team member
- Anomaly detection engine (`app/analytics/anomaly_engine.py`) triggering alert

### Step 2 — Triage

On-call engineer:
1. Acknowledge alert in PagerDuty within SLA window
2. Check `/health/deep` endpoint for system status
3. Check `audit_logs` for correlated events around incident time:
   ```sql
   SELECT * FROM audit_logs
   WHERE org_id = '<affected_org>'
     AND created_at > NOW() - INTERVAL '1 hour'
   ORDER BY created_at DESC;
   ```
4. Determine blast radius (which tenants affected)

### Step 3 — Containment

| Incident Type | Containment Action |
|---|---|
| Auth bypass suspected | Rotate `JWT_SECRET_KEY` immediately; invalidates all active tokens |
| RLS bypass suspected | Disable affected org: `UPDATE organizations SET is_active = false WHERE id = '<id>'` |
| DB credentials leaked | Rotate DB password; restart all pods |
| Service under attack | Enable Cloudflare rate limiting; block IP ranges at ingress |
| Kubernetes pod crash loop | Rollback to previous version: `helm rollback aiops-bot` |

### Step 4 — Eradication

1. Identify root cause from logs and traces
2. Deploy patch via PR → CI → staging → production
3. Blue/green rollback if patch unavailable: `helm upgrade aiops-bot . --set services.apiGateway.blueGreen.activeVersion=blue`
4. Verify health probes pass after patch: `kubectl get pods -n production`

### Step 5 — Recovery

1. Re-enable affected org if disabled during containment
2. Verify RLS still effective via: `pytest tests/test_rls_isolation.py -v`
3. Notify affected customers within 72 hours (GDPR requirement)
4. Update audit log with incident resolution entry

### Step 6 — Post-Incident Review

Within 5 business days:
- Root cause analysis document written
- Control gap identified and remediated
- Evidence added to this document
- Recurring check added to monitoring if not already present

---

## CC2.2 — Communication of Security Incidents

**Requirement:** Security incidents are communicated to affected parties.

**Implementation:**
- Customers notified via email within 72 hours of confirmed data incident (GDPR Article 33/34)
- Internal incident channel: Slack `#incidents`
- Status page updated within 30 minutes of P0/P1 (status.resilo.io)
- Notification service supports: Slack, email, Discord (`app/integrations/notification_service.py`)

---

## CC4.1 — Monitoring and Continuous Improvement

**Requirement:** Controls are monitored and deficiencies are communicated.

**Monthly Security Review Checklist:**
- [ ] Review `audit_logs` for anomalous access patterns
- [ ] Verify no cross-tenant data in Prometheus metrics (org_id label present on all metrics)
- [ ] Run `pytest tests/test_rls_isolation.py tests/test_sso_flow.py tests/test_pricing_limits.py -v`
- [ ] Verify secret rotation schedule (JWT: 90 days, ENCRYPTION_KEY: 180 days)
- [ ] Review Kubernetes RBAC — no new permissive role bindings
- [ ] Check `cert-manager` certificate expiry dates

---

## Incident Log

| Date | Severity | Description | RCA | Status |
|---|---|---|---|---|
| — | — | No incidents recorded at time of SOC2 review | — | — |

*Update this log immediately on any incident.*

---

*This document is part of the Resilo SOC2 Type I evidence package.*
