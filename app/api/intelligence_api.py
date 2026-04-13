"""
intelligence_api.py — AI intelligence layer for Resilo AIOps.

Endpoints:
  GET  /api/v1/anomalies/detect                   — rolling z-score anomaly detection
  GET  /api/v1/remediation/{rec_id}/effectiveness — before/after metric comparison
  GET  /api/v1/insights/explain                   — rule-based root cause analysis
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.runtime import _now, _require_access_token
from app.core.database import (
    Agent, AlertRecord, MetricSnapshot, Organization,
    RemediationRecord, get_db,
)

ANOMALY_WINDOW      = 10    # rolling window size (samples)
ANOMALY_ZSCORE_WARN = 2.5   # z-score → warning anomaly
ANOMALY_ZSCORE_CRIT = 4.0   # z-score → critical anomaly
INSIGHT_ALERT_WINDOW_H = 3  # hours to look back for insight analysis


# ── Shared maths ──────────────────────────────────────────────────────────────

def _mean(v: list[float]) -> float:
    return sum(v) / len(v) if v else 0.0

def _std(v: list[float]) -> float:
    if len(v) < 2:
        return 0.0
    m = _mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


# ── Anomaly helpers ───────────────────────────────────────────────────────────

def _adaptive_threshold(baseline: list[float], base_threshold: float) -> float:
    """Scale threshold up for noisy signals to reduce false positives.
    Uses coefficient-of-variation: a signal with CV > 0.3 gets up to +50% threshold.
    """
    if len(baseline) < 3:
        return base_threshold
    mu = _mean(baseline)
    if mu <= 0:
        return base_threshold
    cv = _std(baseline) / mu
    factor = 1.0 + min(0.5, cv * 1.5)
    return base_threshold * factor


def _hourly_baseline(snaps: list[Any], metric: str, idx: int) -> Optional[list[float]]:
    """Return values from snaps[:idx] whose hour-of-day matches snaps[idx].
    Returns None when there are fewer than 4 same-hour samples (insufficient for seasonality).
    """
    ts = getattr(snaps[idx], "timestamp", None)
    if ts is None:
        return None
    target_hour = ts.hour
    same_hour: list[float] = []
    for j in range(idx):
        t = getattr(snaps[j], "timestamp", None)
        if t is not None and t.hour == target_hour:
            v = getattr(snaps[j], metric, None)
            if v is not None:
                same_hour.append(float(v))
    return same_hour if len(same_hour) >= 4 else None


def _classify_anomaly(zscore: float, run_len: int) -> str:
    """Classify an anomaly based on its z-score and how long it has persisted."""
    if zscore > 0 and run_len >= 3:
        return "sustained_high"
    if zscore < 0 and run_len >= 3:
        return "sustained_low"
    if zscore > 0:
        return "spike"
    if zscore < 0:
        return "sudden_drop"
    return "anomaly"

def _detect_oscillation(zscores: list[float], idx: int, lookback: int = 5) -> bool:
    """True if the recent z-scores alternate sign (oscillating signal)."""
    window = zscores[max(0, idx - lookback): idx + 1]
    if len(window) < 4:
        return False
    sign_changes = sum(
        1 for i in range(1, len(window))
        if (window[i] > 0) != (window[i - 1] > 0)
    )
    return sign_changes >= 3

def _run_anomaly_detection(
    snaps: list[Any],
    metric: str,
) -> list[dict[str, Any]]:
    """
    Rolling z-score anomaly detection with adaptive thresholds and seasonality.

    Baseline selection (in priority order):
      1. Same-hour-of-day samples (seasonality) — when >=4 exist
      2. Rolling window of last ANOMALY_WINDOW samples

    Threshold: scaled up for noisy signals via coefficient-of-variation.
    """
    values = [getattr(s, metric, None) or 0.0 for s in snaps]
    anomalies: list[dict[str, Any]] = []
    zscores: list[float] = [0.0] * len(values)
    run_len = 0

    for i in range(len(values)):
        # ── Baseline selection ────────────────────────────────────────────────
        hourly = _hourly_baseline(snaps, metric, i)
        if hourly is not None:
            baseline = hourly
            baseline_type = "hourly"
        else:
            window_start = max(0, i - ANOMALY_WINDOW)
            baseline = values[window_start:i]
            baseline_type = "rolling"

        if len(baseline) < 3:
            continue

        mu  = _mean(baseline)
        std = _std(baseline)
        if std < 0.1:   # flat signal — no deviation possible
            run_len = 0
            continue

        z = (values[i] - mu) / std
        zscores[i] = z

        # ── Adaptive threshold ────────────────────────────────────────────────
        eff_warn = _adaptive_threshold(baseline, ANOMALY_ZSCORE_WARN)
        eff_crit = _adaptive_threshold(baseline, ANOMALY_ZSCORE_CRIT)

        if abs(z) < eff_warn:
            run_len = 0
            continue

        # Detect run length
        if run_len > 0 and (z > 0) == (zscores[i - 1] > 0):
            run_len += 1
        else:
            run_len = 1

        atype = (
            "oscillating"
            if _detect_oscillation(zscores, i)
            else _classify_anomaly(z, run_len)
        )
        severity = "critical" if abs(z) >= eff_crit else "warning"
        ts = snaps[i].timestamp
        anomalies.append({
            "metric":             metric,
            "value":              round(values[i], 2),
            "baseline_mean":      round(mu, 2),
            "baseline_std":       round(std, 2),
            "zscore":             round(z, 2),
            "baseline_type":      baseline_type,
            "adaptive_threshold": round(eff_warn, 2),
            "severity":           severity,
            "type":               atype,
            "run_length":         run_len,
            "timestamp":          ts.isoformat() if ts else None,
            "agent_id":           snaps[i].agent_id,
        })

    return anomalies


# ── Remediation effectiveness ─────────────────────────────────────────────────

def _effectiveness(
    before: Optional[dict[str, Any]],
    after: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """
    Compute metric improvements from before→after snapshot dicts.
    Returns None if neither exists.
    """
    if not before and not after:
        return None

    metrics_to_check = ["cpu", "memory", "disk", "error_rate", "network_in", "network_out"]
    improvements: dict[str, float] = {}

    for m in metrics_to_check:
        b_val = (before or {}).get(m)
        a_val = (after or {}).get(m)
        if b_val is not None and a_val is not None and float(b_val) > 0:
            pct_change = ((float(b_val) - float(a_val)) / float(b_val)) * 100
            improvements[m] = round(pct_change, 1)

    if not improvements:
        return None

    avg = _mean(list(improvements.values()))
    # Score: 100 = perfect fix, 0 = no change, negative = made worse
    score = round(max(-100.0, min(100.0, avg)), 1)

    verdict: str
    if score >= 20:
        verdict = "effective"
    elif score >= 5:
        verdict = "partially_effective"
    elif score >= -5:
        verdict = "inconclusive"
    else:
        verdict = "worsened"

    return {
        "score":       score,
        "verdict":     verdict,
        "improvements": improvements,
        "before":      before,
        "after":       after,
    }


# ── Insight rules ─────────────────────────────────────────────────────────────

def _explain_metrics(snap: Optional[MetricSnapshot]) -> list[dict[str, Any]]:
    if not snap:
        return []
    insights = []

    cpu = snap.cpu or 0
    mem = snap.memory or 0
    dsk = snap.disk or 0

    if cpu > 80 and mem > 80:
        cpu_excess = (cpu - 80) / 20       # 0–1 over threshold range
        mem_excess = (mem - 80) / 20
        confidence = round(min(1.0, (cpu_excess + mem_excess) / 2 + 0.4), 2)
        insights.append({
            "type":           "resource_exhaustion",
            "severity":       "critical" if cpu > 90 or mem > 90 else "warning",
            "confidence":     confidence,
            "signals":        [f"cpu={cpu:.0f}%", f"memory={mem:.0f}%", "co-elevation"],
            "title":          f"CPU ({cpu:.0f}%) + Memory ({mem:.0f}%) both elevated",
            "explanation":    (
                f"Simultaneous CPU and memory pressure (CPU {cpu:.0f}%, memory {mem:.0f}%) "
                "typically indicates resource contention or a memory-intensive workload "
                "forcing excessive page swapping. This is not two independent issues — "
                "the memory pressure is likely causing the CPU overhead."
            ),
            "recommendation": (
                "1. Profile the top memory-consuming processes — look for leaks. "
                "2. Check if a batch job or scheduled task is running. "
                "3. Consider scaling horizontally if this is sustained."
            ),
        })
    elif cpu > 85:
        confidence = round(min(1.0, 0.5 + (cpu - 85) / 20), 2)
        insights.append({
            "type":           "cpu_saturation",
            "severity":       "critical" if cpu > 95 else "warning",
            "confidence":     confidence,
            "signals":        [f"cpu={cpu:.0f}%", f"headroom={(100 - cpu):.0f}%"],
            "title":          f"CPU saturation at {cpu:.0f}%",
            "explanation":    (
                f"CPU is at {cpu:.0f}%, leaving only {100 - cpu:.0f}% headroom. "
                "This can cause request queuing, increased latency, and timeout errors. "
                "If memory is normal, this suggests a compute-bound workload spike."
            ),
            "recommendation": (
                "1. Identify the top CPU consumer via /processes. "
                "2. Check for runaway loops or unbounded queries. "
                "3. Auto-scale trigger should have fired — verify remediation log."
            ),
        })
    elif mem > 88:
        asymmetry = (mem - cpu) / 100  # stronger asymmetry = higher leak confidence
        confidence = round(min(1.0, 0.45 + asymmetry + (mem - 88) / 24), 2)
        insights.append({
            "type":           "memory_leak",
            "severity":       "warning",
            "confidence":     confidence,
            "signals":        [f"memory={mem:.0f}%", f"cpu={cpu:.0f}%", "cpu_mem_asymmetry"],
            "title":          f"Memory at {mem:.0f}% — potential leak signature",
            "explanation":    (
                f"Memory is at {mem:.0f}% while CPU is normal ({cpu:.0f}%). "
                "This asymmetry (high memory, low CPU) is a classic memory leak signature. "
                "The process is consuming memory without proportional CPU work."
            ),
            "recommendation": (
                "1. Check process memory over time — look for steady growth. "
                "2. Run a heap profiler if possible. "
                "3. Rolling restart may provide temporary relief while root cause is identified."
            ),
        })

    if dsk > 85:
        likely_cause = "log accumulation" if dsk < 95 else "data growth or log spiral"
        confidence = round(min(1.0, 0.6 + (dsk - 85) / 30), 2)
        insights.append({
            "type":           "disk_pressure",
            "severity":       "critical" if dsk > 92 else "warning",
            "confidence":     confidence,
            "signals":        [f"disk={dsk:.0f}%", likely_cause],
            "title":          f"Disk at {dsk:.0f}% — {likely_cause}",
            "explanation":    (
                f"Disk usage at {dsk:.0f}%. At this level, write operations begin failing "
                "and databases may go into read-only mode. "
                f"Likely cause: {likely_cause}."
            ),
            "recommendation": (
                "1. Run log cleanup playbook immediately. "
                "2. Check for core dump files or large temp files. "
                "3. Consider log rotation policy if not configured."
            ),
        })

    return insights


def _explain_alerts(alerts: list[AlertRecord]) -> list[dict[str, Any]]:
    if not alerts:
        return []
    insights = []
    by_cat = Counter(a.category for a in alerts)
    by_agent: dict[str, int] = Counter(a.agent_id for a in alerts if a.agent_id)
    by_severity = Counter(a.severity for a in alerts)

    # Pattern: same category fires multiple times
    dominant_cat, dominant_count = by_cat.most_common(1)[0]
    if dominant_count >= 3:
        confidence = round(min(1.0, 0.4 + dominant_count / 10), 2)
        insights.append({
            "type":           "recurring_alert_pattern",
            "severity":       "warning",
            "confidence":     confidence,
            "signals":        [f"category={dominant_cat}", f"count={dominant_count}", "recurrence"],
            "title":          f"{dominant_count} {dominant_cat} alerts — systemic issue",
            "explanation":    (
                f"{dominant_count} alerts for the '{dominant_cat}' category fired in the "
                f"last {INSIGHT_ALERT_WINDOW_H}h. Recurrence at this frequency indicates "
                "a systemic condition rather than a transient spike — the underlying cause "
                "has not been resolved by previous remediation attempts."
            ),
            "recommendation": (
                f"1. Review the remediation log for '{dominant_cat}' actions — check effectiveness scores. "
                "2. Raise the auto-remediation threshold if false positives are occurring. "
                "3. Escalate to an on-call engineer if automated fixes have been exhausted."
            ),
        })

    # Pattern: same agent causing many alerts → noisy neighbor
    if by_agent:
        noisy_agent, noisy_count = max(by_agent.items(), key=lambda kv: kv[1])
        if noisy_count >= 3:
            confidence = round(min(1.0, 0.4 + noisy_count / 10), 2)
            insights.append({
                "type":           "noisy_neighbor",
                "severity":       "warning",
                "confidence":     confidence,
                "signals":        [f"agent={noisy_agent[:8]}", f"alert_count={noisy_count}", "concentration"],
                "title":          f"Agent {noisy_agent[:8]}… is responsible for {noisy_count} alerts",
                "explanation":    (
                    f"A single agent (ID: {noisy_agent}) has generated {noisy_count} alerts. "
                    "This noisy-neighbor pattern can indicate: (a) the agent is on overloaded hardware, "
                    "(b) a tenant workload is consuming disproportionate shared resources, "
                    "or (c) the agent is misconfigured."
                ),
                "recommendation": (
                    f"1. Inspect agent {noisy_agent[:8]} directly — check its platform_info. "
                    "2. Compare its metrics to other agents on the same host. "
                    "3. Consider migrating the agent to isolated infrastructure."
                ),
            })

    # Pattern: critical severity dominates
    crit_count = by_severity.get("critical", 0)
    if crit_count >= 2:
        confidence = round(min(1.0, 0.5 + crit_count / 8), 2)
        insights.append({
            "type":           "critical_storm",
            "severity":       "critical",
            "confidence":     confidence,
            "signals":        [f"critical_count={crit_count}", "alert_storm", "cascade_risk"],
            "title":          f"{crit_count} critical alerts — alert storm in progress",
            "explanation":    (
                f"{crit_count} critical-severity alerts have fired. An alert storm often "
                "indicates cascading failures where one root cause triggers multiple "
                "downstream alert conditions. Treating each alert individually is ineffective."
            ),
            "recommendation": (
                "1. Identify the FIRST alert in the sequence — that is likely the root cause. "
                "2. Silence downstream alerts while root cause is mitigated. "
                "3. Declare an incident (use Declare Incident button) to coordinate response."
            ),
        })

    return insights


def _explain_remediation(remediations: list[RemediationRecord]) -> list[dict[str, Any]]:
    if not remediations:
        return []
    insights = []

    failures = [r for r in remediations if r.status == "failed"]
    if len(failures) >= 2:
        failed_actions = Counter(r.action for r in failures)
        action, count = failed_actions.most_common(1)[0]
        confidence = round(min(1.0, 0.5 + count / 6), 2)
        insights.append({
            "type":           "repeated_remediation_failure",
            "severity":       "critical",
            "confidence":     confidence,
            "signals":        [f"action={action}", f"failures={count}", "playbook_ineffective"],
            "title":          f"Remediation '{action}' failed {count}× — escalation needed",
            "explanation":    (
                f"The automated remediation action '{action}' has failed {count} times recently. "
                "Repeated failure indicates the issue is outside the scope of the configured playbook "
                "— either the environment has changed, or the playbook logic is incorrect for this condition."
            ),
            "recommendation": (
                f"1. Review the error log for '{action}' in the remediation feed. "
                "2. Verify the playbook's prerequisites are still met. "
                "3. Manually intervene and update the playbook after resolution."
            ),
        })

    # Check effectiveness if before/after exists
    effective_count = sum(
        1 for r in remediations
        if r.status == "success" and r.after_metrics and r.before_metrics
    )
    failed_effective = [
        r for r in remediations
        if r.status == "success" and r.before_metrics and r.after_metrics
        and (r.before_metrics.get("cpu", 0) - r.after_metrics.get("cpu", 0)) < 5
    ]
    if failed_effective:
        confidence = round(min(1.0, 0.45 + len(failed_effective) / 6), 2)
        insights.append({
            "type":           "ineffective_remediation",
            "severity":       "warning",
            "confidence":     confidence,
            "signals":        [f"ineffective_count={len(failed_effective)}", "metric_unchanged", "symptom_treatment"],
            "title":          f"{len(failed_effective)} remediation(s) ran but metrics didn't improve",
            "explanation":    (
                f"{len(failed_effective)} remediations completed successfully but the target metric "
                "did not improve significantly. This suggests the remediation action addresses a symptom, "
                "not the actual root cause."
            ),
            "recommendation": (
                "1. Review what these remediations actually do (kill process, clear cache, restart service). "
                "2. Investigate whether the root cause is deeper (e.g., unbounded queue, external dependency). "
                "3. Consider adding a more targeted playbook for this condition."
            ),
        })

    return insights


# ── Router ────────────────────────────────────────────────────────────────────

def build_intelligence_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    # ── 1. Anomaly detection ──────────────────────────────────────────────────

    @router.get("/anomalies/detect")
    async def detect_anomalies(
        request: Request,
        limit: int = 60,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_access_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        result = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.org_id == org_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(limit)
        )
        raw_snaps = result.scalars().all()

        # Group per agent — z-scores must never cross agent boundaries
        by_agent: dict[str, list[Any]] = defaultdict(list)
        for s in reversed(raw_snaps):   # oldest first within each agent
            by_agent[s.agent_id].append(s)

        all_anomalies: list[dict[str, Any]] = []
        for agent_snaps in by_agent.values():
            for metric in ("cpu", "memory", "disk"):
                all_anomalies.extend(_run_anomaly_detection(agent_snaps, metric))

        # Sort by timestamp descending for the UI feed
        all_anomalies.sort(key=lambda a: a.get("timestamp") or "", reverse=True)

        # Summary stats
        by_severity = Counter(a["severity"] for a in all_anomalies)
        by_type     = Counter(a["type"]     for a in all_anomalies)

        return {
            "anomalies": all_anomalies,
            "total":     len(all_anomalies),
            "summary": {
                "critical": by_severity.get("critical", 0),
                "warning":  by_severity.get("warning",  0),
                "by_type":  dict(by_type),
            },
            "sample_count": len(snaps),
        }

    # ── 2. Remediation effectiveness ─────────────────────────────────────────

    @router.get("/remediation/{rec_id}/effectiveness")
    async def remediation_effectiveness(
        rec_id: str,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_access_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        result = await db.execute(
            select(RemediationRecord)
            .where(RemediationRecord.id == rec_id, RemediationRecord.org_id == org_id)
        )
        rec = result.scalar_one_or_none()
        if rec is None:
            raise HTTPException(status_code=404, detail="Remediation record not found")

        before = rec.before_metrics
        after  = rec.after_metrics

        # Fallback: if after_metrics not stored, fetch the MetricSnapshot
        # closest to 5 minutes after the remediation completed
        if after is None and rec.completed_at and rec.agent_id:
            target_time = rec.completed_at + timedelta(minutes=5)
            snap_result = await db.execute(
                select(MetricSnapshot)
                .where(
                    MetricSnapshot.org_id   == org_id,
                    MetricSnapshot.agent_id == rec.agent_id,
                    MetricSnapshot.timestamp >= rec.completed_at,
                )
                .order_by(MetricSnapshot.timestamp)
                .limit(1)
            )
            snap = snap_result.scalar_one_or_none()
            if snap:
                after = {
                    "cpu":    snap.cpu,
                    "memory": snap.memory,
                    "disk":   snap.disk,
                    "note":   f"fetched from metric snapshot at {snap.timestamp.isoformat()}",
                }

        eff = _effectiveness(before, after)
        return {
            "remediation_id": rec.id,
            "action":         rec.action,
            "status":         rec.status,
            "effectiveness":  eff,
            "has_before":     before is not None,
            "has_after":      after  is not None,
        }

    # ── 3. Insight explainer (root cause analysis) ────────────────────────────

    @router.get("/insights/explain")
    async def explain_insights(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_access_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        window = _now() - timedelta(hours=INSIGHT_ALERT_WINDOW_H)

        # Fetch recent data
        snap_result = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.org_id == org_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(1)
        )
        latest_snap = snap_result.scalar_one_or_none()

        alerts_result = await db.execute(
            select(AlertRecord)
            .where(AlertRecord.org_id == org_id, AlertRecord.created_at >= window)
            .order_by(desc(AlertRecord.created_at))
            .limit(50)
        )
        recent_alerts = alerts_result.scalars().all()

        rem_result = await db.execute(
            select(RemediationRecord)
            .where(RemediationRecord.org_id == org_id, RemediationRecord.created_at >= window)
            .order_by(desc(RemediationRecord.created_at))
            .limit(30)
        )
        recent_rems = rem_result.scalars().all()

        # Aggregate insights from all rule engines
        insights: list[dict[str, Any]] = []
        insights.extend(_explain_metrics(latest_snap))
        insights.extend(_explain_alerts(recent_alerts))
        insights.extend(_explain_remediation(recent_rems))

        # Deduplicate by type (keep highest severity per type)
        seen: dict[str, dict[str, Any]] = {}
        sev_rank = {"critical": 2, "warning": 1, "info": 0}
        for ins in insights:
            t = ins["type"]
            if t not in seen or sev_rank.get(ins["severity"], 0) > sev_rank.get(seen[t]["severity"], 0):
                seen[t] = ins
        final_insights = sorted(seen.values(), key=lambda i: -sev_rank.get(i["severity"], 0))

        return {
            "insights":         final_insights,
            "total":            len(final_insights),
            "analysed_alerts":  len(recent_alerts),
            "analysed_actions": len(recent_rems),
            "window_hours":     INSIGHT_ALERT_WINDOW_H,
            "generated_at":     _now().isoformat(),
        }

    return router
