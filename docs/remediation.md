# Remediation System

## Purpose

Translate investigation conclusions into safe, audited, operator-controlled actions. The system never executes destructive actions automatically without both high confidence and explicit safe-list membership.

---

## Routing Tiers

After RCA, the investigation engine calls `_route_action(confidence)`:

| Confidence | Routing | Meaning |
|---|---|---|
| ≥ 0.85 | `auto_execute` | High confidence — execute immediately if action is safe-listed |
| ≥ 0.60 | `manual_approval` | Medium confidence — queue for operator review |
| < 0.60 | `investigation_only` | Low confidence — record finding, no action |

**Hard override:** `confidence < 0.75` → forces `manual_approval` regardless of routing tier. This prevents a high-confidence-but-wrong LLM from auto-executing.

---

## Safe-List

Only explicitly named services may be auto-restarted:

```python
PROTECTED_SERVICES = {"nginx", "postgres", "redis", "celery", "gunicorn"}
```

Actions outside this list → `investigation_only` even at 95% confidence.

Auto-restart rate limiting: max 3 restarts per service per hour. Tracked in `AgentActionLog`.

---

## Action Types

| Action | Tier | Description |
|---|---|---|
| `restart_service` | auto_execute (if safe-listed) | systemctl restart |
| `kill_process` | manual_approval | kill -9 on named PID |
| `terminate_db_connection` | manual_approval | pg_terminate_backend |
| `clear_disk_space` | manual_approval | remove identified log/temp files |
| `rotate_logs` | auto_execute | logrotate on named path |
| `investigate_only` | — | No action, record findings |

---

## Approval Flow

```
Investigation completes → manual_approval
         ↓
Remediation job created (status=queued) in remediation_jobs table
         ↓
Operator sees job on /approvals page
         ↓
Approve → job transitions: queued → running → completed|failed
Reject  → job transitions: queued → rejected, reason recorded
         ↓
Agent executes action on target host
         ↓
Result reported back → action_log updated
```

Approval notifications pushed via SSE to all authenticated sessions.

---

## Audit Trail

Every remediation action is recorded in `AgentActionLog`:

```sql
agent_id, action, target, outcome, confidence,
decision_source, contributing_process,
queued_at, executed_at, completed_at
```

`decision_source` distinguishes LLM decisions from rule-based fallbacks.

`contributing_process` stores the specific process name/PID that triggered the action (e.g. `python3:4421`).

---

## Action Success Rate Feedback

The LLM analysis prompt includes historical action success rates:

```
restart_service nginx: 8/9 (88%)
kill_process: 5/6 (83%)
```

This biases the LLM toward actions that have historically worked on this specific agent, improving recommendation quality over time.

---

## Remediation Jobs API

```
POST   /api/remediation/jobs          Create a job (from investigation result)
GET    /api/remediation/jobs          List jobs (with status filter)
GET    /api/remediation/jobs/{id}     Job detail
POST   /api/remediation/jobs/{id}/approve    Approve
POST   /api/remediation/jobs/{id}/reject     Reject
GET    /api/remediation/jobs/{id}/result     Post-execution result
```

---

## Failure Handling

If an auto-executed action fails (non-zero exit, timeout, or exception):
1. Job status → `failed`, error stored
2. Routing upgraded to `manual_approval` for the next occurrence
3. Alert remains open until manual resolution
4. Investigation result preserved for post-mortem analysis
