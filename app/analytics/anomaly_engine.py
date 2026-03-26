"""
anomaly_engine.py — Agentic Anomaly Detection & Automated Remediation Engine

Background async task started by core_api.py on startup.

Pipeline per cycle (default every 30s):
    1. Fetch latest MetricSnapshot per (org, agent)
    2. Check built-in thresholds + user-defined AlertRules → detect anomalies
    3. Create AlertRecord (deduplicated — no duplicate within cooldown window)
    4. Dispatch real-time notifications via notification_service
    5. Match alert → remediation rule
    6. If autonomous_mode enabled for org: execute remediation command on agent
    7. Schedule verification after VERIFY_DELAY_SECS
    8. Update RemediationRecord + AlertRecord with outcome
    9. Write AuditLog for every significant step

Daily summary scheduler:
    Runs a background task that wakes up every hour, checks if it is the
    configured summary hour (DAILY_SUMMARY_HOUR, default 8 UTC), and if so
    sends a digest via notification_service.dispatch_daily_summary().

Environment variables:
    ANOMALY_POLL_INTERVAL   seconds between detection cycles (default: 30)
    ANOMALY_VERIFY_DELAY    seconds before verifying remediation outcome (default: 60)
    ANOMALY_AUTONOMOUS      global autonomous mode: "true"|"false"|"org" (default: org)
    DAILY_SUMMARY_HOUR      UTC hour (0-23) to dispatch daily summary (default: 8)
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    SessionLocal, Organization, Agent,
    MetricSnapshot, AlertRecord, RemediationRecord, AuditLog,
    AlertRule,
)

log = logging.getLogger("anomaly_engine")

POLL_INTERVAL       = int(os.getenv("ANOMALY_POLL_INTERVAL", "30"))
VERIFY_DELAY        = int(os.getenv("ANOMALY_VERIFY_DELAY", "60"))
AUTONOMOUS_MODE     = os.getenv("ANOMALY_AUTONOMOUS", "org")   # org | true | false
DAILY_SUMMARY_HOUR  = int(os.getenv("DAILY_SUMMARY_HOUR", "8"))

# ── Built-in threshold definitions ────────────────────────────────────────────
# (category, metric_attr, high_threshold, critical_threshold)

THRESHOLDS = [
    ("cpu",    "cpu",    85.0, 95.0),
    ("memory", "memory", 80.0, 92.0),
    ("disk",   "disk",   85.0, 95.0),
]

# ── Remediation rule table ────────────────────────────────────────────────────
# Maps (category, severity) → (action, params)

REMEDIATION_RULES: dict[tuple, tuple] = {
    ("cpu",    "high"):     ("free_memory",   {}),
    ("cpu",    "critical"): ("clear_cache",   {}),
    ("memory", "high"):     ("run_gc",        {}),
    ("memory", "critical"): ("free_memory",   {}),
    ("disk",   "high"):     ("disk_cleanup",  {}),
    ("disk",   "critical"): ("disk_cleanup",  {"aggressive": True}),
}

# ── Dedup window ──────────────────────────────────────────────────────────────
DEDUP_WINDOW_MINS = 5  # built-in: no duplicate alert within this window

# Track which summary hours we have already sent for (org_id → date string)
_summary_sent: dict[str, str] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Engine entry points
# ─────────────────────────────────────────────────────────────────────────────

async def start_anomaly_engine() -> None:
    """Called by core_api.py startup. Runs detection loop forever in background."""
    log.info(
        "Anomaly engine starting (poll=%ds, verify=%ds, autonomous=%s, summary_hour=%d UTC)",
        POLL_INTERVAL, VERIFY_DELAY, AUTONOMOUS_MODE, DAILY_SUMMARY_HOUR,
    )
    while True:
        try:
            await _run_cycle()
        except Exception as exc:
            log.error("Anomaly engine cycle error: %s", exc, exc_info=True)
        await asyncio.sleep(POLL_INTERVAL)


async def start_daily_summary_scheduler() -> None:
    """
    Wakes up every 10 minutes, checks if it is the daily summary hour (UTC),
    and dispatches one digest per org that has not yet received one today.
    """
    # Import here to avoid circular dependency at module load
    from notification_service import dispatch_daily_summary

    log.info("Daily summary scheduler starting (target hour=%d UTC)", DAILY_SUMMARY_HOUR)
    while True:
        await asyncio.sleep(600)  # check every 10 minutes
        now = datetime.now(timezone.utc)
        if now.hour != DAILY_SUMMARY_HOUR:
            continue

        today = now.strftime("%Y-%m-%d")
        try:
            async with SessionLocal() as db:
                orgs_result = await db.execute(
                    select(Organization).where(Organization.is_active == True)
                )
                for org in orgs_result.scalars().all():
                    if _summary_sent.get(org.id) == today:
                        continue  # already sent today
                    try:
                        await dispatch_daily_summary(db, org.id)
                        _summary_sent[org.id] = today
                        log.info("Daily summary dispatched: org=%s date=%s", org.id[:8], today)
                    except Exception as exc:
                        log.error("Daily summary failed for org=%s: %s", org.id[:8], exc)
        except Exception as exc:
            log.error("Daily summary scheduler error: %s", exc, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main cycle
# ─────────────────────────────────────────────────────────────────────────────

async def _run_cycle() -> None:
    # Import here to avoid circular import at module level
    from notification_service import dispatch_alert_notification

    async with SessionLocal() as db:
        snapshots = await _fetch_latest_snapshots(db)
        if not snapshots:
            return

        # Fetch all active custom alert rules for the orgs represented in snapshots
        org_ids = list({s.org_id for s in snapshots})
        custom_rules = await _fetch_alert_rules(db, org_ids)

        for snap in snapshots:
            # ── Built-in threshold checks ─────────────────────────────────
            breaches = _check_thresholds(snap)

            # ── Custom rule checks ────────────────────────────────────────
            custom_breaches = await _check_custom_rules(db, snap, custom_rules)

            # Merge: custom rules override built-in if they cover the same category
            custom_categories = {b[0] for b in custom_breaches}
            merged_breaches = [b for b in breaches if b[0] not in custom_categories]
            merged_breaches.extend(custom_breaches)

            for category, value, threshold, severity in merged_breaches:
                agent_result = await db.execute(
                    select(Agent).where(Agent.id == snap.agent_id)
                )
                agent = agent_result.scalar_one_or_none()
                agent_label = agent.label if agent else snap.agent_id[:8]

                alert = await _get_or_create_alert(
                    db, snap, category, value, threshold, severity
                )
                if alert is None:
                    continue  # deduped — skip notifications too

                # Dispatch notifications asynchronously (non-blocking)
                asyncio.create_task(
                    _safe_notify(snap.org_id, alert, agent_label)
                )

                # ── Autonomous remediation ────────────────────────────────
                if not await _autonomous_enabled(db, snap.org_id):
                    continue

                action_key = (category, severity)
                if action_key not in REMEDIATION_RULES:
                    continue

                action, params = REMEDIATION_RULES[action_key]
                record = await _create_remediation(db, snap, alert, action, params)

                # Schedule verification (non-blocking)
                asyncio.create_task(_verify_later(record.id, snap.agent_id, category))


async def _safe_notify(org_id: str, alert: AlertRecord, agent_label: str) -> None:
    """Wrapper so notification errors never crash the detection cycle."""
    from notification_service import dispatch_alert_notification
    try:
        async with SessionLocal() as db:
            await dispatch_alert_notification(db, org_id, alert, agent_label)
    except Exception as exc:
        log.error("Notification dispatch error: org=%s alert=%s: %s",
                  org_id[:8], alert.id[:8], exc)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Fetch latest snapshot per (org, agent)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_latest_snapshots(db: AsyncSession) -> list[MetricSnapshot]:
    """
    Returns the most recent MetricSnapshot for each active agent,
    limited to snapshots newer than 2 × POLL_INTERVAL.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=POLL_INTERVAL * 2)

    # Subquery: max timestamp per agent
    sub = (
        select(
            MetricSnapshot.agent_id,
            sqlfunc.max(MetricSnapshot.timestamp).label("max_ts"),
        )
        .where(MetricSnapshot.timestamp >= cutoff)
        .group_by(MetricSnapshot.agent_id)
        .subquery()
    )

    result = await db.execute(
        select(MetricSnapshot).join(
            sub,
            (MetricSnapshot.agent_id == sub.c.agent_id)
            & (MetricSnapshot.timestamp == sub.c.max_ts),
        )
    )
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Threshold checks (built-in + custom rules)
# ─────────────────────────────────────────────────────────────────────────────

def _check_thresholds(snap: MetricSnapshot) -> list[tuple]:
    """Built-in threshold check. Returns (category, value, threshold, severity)."""
    breaches = []
    for category, attr, high, critical in THRESHOLDS:
        value = getattr(snap, attr, None)
        if value is None:
            continue
        if value >= critical:
            breaches.append((category, value, critical, "critical"))
        elif value >= high:
            breaches.append((category, value, high, "high"))
    return breaches


async def _fetch_alert_rules(
    db: AsyncSession, org_ids: list[str]
) -> list[AlertRule]:
    """Load all enabled custom AlertRules for the given orgs."""
    if not org_ids:
        return []
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.org_id.in_(org_ids),
            AlertRule.enabled == True,
        )
    )
    return list(result.scalars().all())


async def _check_custom_rules(
    db: AsyncSession,
    snap: MetricSnapshot,
    rules: list[AlertRule],
) -> list[tuple]:
    """
    Evaluate user-defined AlertRules against a snapshot.
    Returns (category, value, threshold, severity) for each triggered rule,
    honouring per-rule cooldown windows.
    """
    breaches = []
    for rule in rules:
        # Scope: org must match; agent_id None = global (all agents)
        if rule.org_id != snap.org_id:
            continue
        if rule.agent_id and rule.agent_id != snap.agent_id:
            continue

        value = getattr(snap, rule.metric, None)
        if value is None:
            continue
        if value < rule.threshold:
            continue

        # Per-rule dedup: check cooldown
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=rule.cooldown_minutes)
        existing = await db.execute(
            select(AlertRecord).where(
                AlertRecord.org_id    == snap.org_id,
                AlertRecord.agent_id  == snap.agent_id,
                AlertRecord.category  == rule.metric,
                AlertRecord.status    == "open",
                AlertRecord.created_at >= cooldown_cutoff,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue  # within cooldown

        breaches.append((rule.metric, value, rule.threshold, rule.severity))

    return breaches


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Deduplicated alert creation
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_create_alert(
    db: AsyncSession,
    snap: MetricSnapshot,
    category: str,
    value: float,
    threshold: float,
    severity: str,
) -> Optional[AlertRecord]:
    """
    Returns a new AlertRecord if no open alert with the same
    (org_id, agent_id, category) exists within DEDUP_WINDOW_MINS.
    Returns None if deduped (existing alert found).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=DEDUP_WINDOW_MINS)

    existing = await db.execute(
        select(AlertRecord).where(
            AlertRecord.org_id   == snap.org_id,
            AlertRecord.agent_id == snap.agent_id,
            AlertRecord.category == category,
            AlertRecord.status   == "open",
            AlertRecord.created_at >= cutoff,
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        return None  # already open, skip

    # Fetch agent label for the title
    agent_result = await db.execute(select(Agent).where(Agent.id == snap.agent_id))
    agent = agent_result.scalar_one_or_none()
    label = agent.label if agent else snap.agent_id[:8]

    alert = AlertRecord(
        id=str(uuid.uuid4()),
        org_id=snap.org_id,
        agent_id=snap.agent_id,
        owner_user_id=agent.owner_user_id if agent else None,
        severity=severity,
        category=category,
        title=f"{category.upper()} {severity.upper()} — {label}",
        detail=(
            f"{category.capitalize()} usage is {value:.1f}% "
            f"(threshold: {threshold:.0f}%) on agent '{label}'"
        ),
        metric_value=value,
        threshold=threshold,
        status="open",
    )
    db.add(alert)

    await _write_audit(db, snap.org_id, action="alert.created", resource_type="alert",
                       resource_id=alert.id, detail={"category": category, "value": value})
    await db.commit()
    await db.refresh(alert)

    log.info("Alert created: org=%s agent=%s category=%s severity=%s value=%.1f",
             snap.org_id[:8], snap.agent_id[:8], category, severity, value)
    return alert


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Check autonomous mode for org
# ─────────────────────────────────────────────────────────────────────────────

async def _autonomous_enabled(db: AsyncSession, org_id: str) -> bool:
    if AUTONOMOUS_MODE == "false":
        return False
    if AUTONOMOUS_MODE == "true":
        return True
    # "org" mode — check org settings
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org or not org.settings:
        return False
    return bool(org.settings.get("autonomous_mode", False))


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Create remediation record and enqueue command
# ─────────────────────────────────────────────────────────────────────────────

async def _create_remediation(
    db: AsyncSession,
    snap: MetricSnapshot,
    alert: AlertRecord,
    action: str,
    params: dict,
) -> RemediationRecord:
    """
    Creates a RemediationRecord and enqueues the command on the Agent.
    The command is delivered piggy-backed in the next heartbeat response.
    """
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    record = RemediationRecord(
        id=record_id,
        org_id=snap.org_id,
        alert_id=alert.id,
        agent_id=snap.agent_id,
        action=action,
        params=params,
        source="auto",
        triggered_by=None,
        status="running",
        before_metrics={
            "cpu": snap.cpu,
            "memory": snap.memory,
            "disk": snap.disk,
        },
        started_at=now,
    )
    db.add(record)

    # Enqueue command on Agent.pending_cmds (delivered on next heartbeat)
    agent_result = await db.execute(select(Agent).where(Agent.id == snap.agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent:
        cmds = list(agent.pending_cmds or [])
        cmds.append({"cmd_id": record_id, "action": action, "params": params})
        agent.pending_cmds = cmds

    await _write_audit(db, snap.org_id, agent_id=snap.agent_id, action="remediation.started",
                       resource_type="remediation", resource_id=record_id,
                       detail={"action": action, "source": "auto", "alert_id": alert.id})
    await db.commit()

    log.info("Remediation queued: org=%s agent=%s action=%s record=%s",
             snap.org_id[:8], snap.agent_id[:8], action, record_id[:8])
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Deferred verification
# ─────────────────────────────────────────────────────────────────────────────

async def _verify_later(record_id: str, agent_id: str, category: str) -> None:
    """
    Waits VERIFY_DELAY seconds, then checks if the metric improved.
    Updates RemediationRecord and AlertRecord accordingly.
    """
    await asyncio.sleep(VERIFY_DELAY)
    try:
        async with SessionLocal() as db:
            await _verify_remediation(db, record_id, agent_id, category)
    except Exception as exc:
        log.error("Verification failed for record %s: %s", record_id[:8], exc)


async def _verify_remediation(
    db: AsyncSession,
    record_id: str,
    agent_id: str,
    category: str,
) -> None:
    # Fetch record
    rec_result = await db.execute(
        select(RemediationRecord).where(RemediationRecord.id == record_id)
    )
    record = rec_result.scalar_one_or_none()
    if not record:
        return

    # Get latest metric snapshot for the agent
    snap_result = await db.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.agent_id == agent_id)
        .order_by(MetricSnapshot.timestamp.desc())
        .limit(1)
    )
    snap = snap_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    record.completed_at = now

    if snap:
        after = {"cpu": snap.cpu, "memory": snap.memory, "disk": snap.disk}
        record.after_metrics = after

        before_value = (record.before_metrics or {}).get(category, 100.0)
        after_value  = after.get(category, before_value)

        improved = after_value < before_value - 3.0  # at least 3% improvement
        record.verified = improved
        record.status   = "success" if improved else "failed"
        record.result   = (
            f"{category.capitalize()} went from {before_value:.1f}% to {after_value:.1f}%"
        )

        # Resolve alert if metric is now below threshold
        if record.alert_id and improved:
            _, _, high, _ = next(
                (t for t in THRESHOLDS if t[0] == category),
                (category, category, 100.0, 100.0)
            )
            if after_value < high:
                alert_result = await db.execute(
                    select(AlertRecord).where(AlertRecord.id == record.alert_id)
                )
                alert = alert_result.scalar_one_or_none()
                if alert and alert.status == "open":
                    alert.status = "resolved"
                    alert.resolved_at = now
    else:
        record.status = "failed"
        record.error  = "No metric snapshot received after remediation"

    await _write_audit(db, record.org_id, agent_id=agent_id, action="remediation.verified",
                       resource_type="remediation", resource_id=record_id,
                       detail={"status": record.status, "category": category})
    await db.commit()

    log.info("Remediation verified: record=%s status=%s", record_id[:8], record.status)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: write audit log
# ─────────────────────────────────────────────────────────────────────────────

async def _write_audit(
    db: AsyncSession,
    org_id: Optional[str],
    *,
    action: str,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        agent_id=agent_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
    ))
