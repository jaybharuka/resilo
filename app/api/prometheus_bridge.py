"""
prometheus_bridge.py — Ingest Prometheus/Grafana alerts and raw metrics.

Endpoints (all mounted under /ingest):
  POST /ingest/prometheus/alertmanager  — Alertmanager webhook
  POST /ingest/prometheus/metrics       — Prometheus text-format scrape push
  POST /ingest/grafana/alert            — Grafana alerting webhook

Auth: Bearer token via PROMETHEUS_WEBHOOK_TOKEN env var.
      If the var is empty the endpoints are unauthenticated (dev mode).

Agent auto-provisioning: unknown instances are registered automatically
with execution_mode="manual_approval" and source="prometheus".
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Agent, MetricSnapshot, Organization, get_db

_log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Auth ──────────────────────────────────────────────────────────────────────

async def _check_prom_auth(request: Request) -> None:
    token = os.getenv("PROMETHEUS_WEBHOOK_TOKEN", "")
    if not token:
        return  # dev mode — accept unauthenticated
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != token:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


# ── Org resolution ────────────────────────────────────────────────────────────

async def _get_default_org_id(db: AsyncSession) -> str:
    result = await db.execute(
        select(Organization).where(
            (Organization.slug == "default") | (Organization.name == "Default Organization")
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=503, detail="No default organization configured")
    return org.id


# ── Agent auto-provisioning ───────────────────────────────────────────────────

async def _get_or_create_prometheus_agent(
    db: AsyncSession, org_id: str, instance: str
) -> Agent:
    """Find or create a Prometheus-sourced agent keyed by instance name."""
    key_hash = hashlib.sha256(
        f"prometheus:{org_id}:{instance}".encode()
    ).hexdigest()
    result = await db.execute(
        select(Agent).where(Agent.key_hash == key_hash, Agent.is_active.is_(True))
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        agent = Agent(
            org_id=org_id,
            label=instance,
            key_hash=key_hash,
            status="live",
            execution_mode="manual_approval",
            source="prometheus",
            platform_info={"hostname": instance, "source": "prometheus"},
        )
        db.add(agent)
        await db.flush()
        _log.info("[prometheus_bridge] provisioned new agent instance=%s id=%s", instance, agent.id)
    else:
        agent.last_seen = _now()
        agent.status = "live"
    return agent


# ── Prometheus text-format parsers ────────────────────────────────────────────

def _extract_metric(raw: str, metric_name: str, **label_filters: str) -> float | None:
    """
    Extract the first matching metric value from Prometheus exposition format.
    label_filters are matched as exact substring  key="value"  inside {}.
    """
    if label_filters:
        prefix = metric_name + "{"
        for line in raw.splitlines():
            if not line.startswith(prefix):
                continue
            if all(f'{k}="{v}"' in line for k, v in label_filters.items()):
                m = re.search(r"\}\s+([\d.e+\-]+)\s*$", line)
                if m:
                    try:
                        return float(m.group(1))
                    except ValueError:
                        pass
    else:
        for line in raw.splitlines():
            if line.startswith(metric_name + " ") or line.startswith(metric_name + "\t"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        return float(parts[1])
                    except ValueError:
                        pass
    return None


def _extract_cpu_idle(raw: str) -> float | None:
    """Compute average idle% across all CPUs from node_cpu_seconds_total counters."""
    idle = 0.0
    total = 0.0
    for line in raw.splitlines():
        if not line.startswith("node_cpu_seconds_total{"):
            continue
        m = re.search(r"\}\s+([\d.e+\-]+)", line)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except ValueError:
            continue
        total += val
        if 'mode="idle"' in line:
            idle += val
    return (idle / total) * 100.0 if total > 0 else None


def _parse_prometheus_text(raw: str, instance: str) -> dict[str, Any]:
    """Parse Prometheus text format into the platform's standard metrics dict."""
    metrics: dict[str, Any] = {}

    mem_total = _extract_metric(raw, "node_memory_MemTotal_bytes")
    mem_avail = _extract_metric(raw, "node_memory_MemAvailable_bytes")
    if mem_total and mem_avail:
        metrics["memory"] = round((1 - mem_avail / mem_total) * 100, 1)
        metrics["memory_total"] = int(mem_total)
        metrics["memory_used"] = int(mem_total - mem_avail)

    disk_avail = _extract_metric(raw, "node_filesystem_avail_bytes", mountpoint="/")
    disk_total = _extract_metric(raw, "node_filesystem_size_bytes", mountpoint="/")
    if disk_total and disk_avail:
        metrics["disk"] = round((1 - disk_avail / disk_total) * 100, 1)

    net_rx = _extract_metric(raw, "node_network_receive_bytes_total", device="eth0")
    net_tx = _extract_metric(raw, "node_network_transmit_bytes_total", device="eth0")
    if net_rx:
        metrics["network_in"] = int(net_rx)
    if net_tx:
        metrics["network_out"] = int(net_tx)

    cpu_idle = _extract_cpu_idle(raw)
    if cpu_idle is not None:
        metrics["cpu"] = round(100 - cpu_idle, 1)

    metrics["timestamp"] = time.time()
    metrics["source"] = "prometheus"
    metrics["instance"] = instance
    return metrics


# ── Alert-text metric extraction ──────────────────────────────────────────────

def _severity_canon(s: str) -> str:
    s = (s or "").lower()
    return s if s in ("critical", "high", "medium", "low", "info") else "high"


def _parse_alert_text(alertname: str, description: str) -> dict[str, float]:
    """Scrape numeric metric values from alert name and free-text description."""
    metrics: dict[str, float] = {}
    text = (alertname + " " + description).lower()

    for pat in (r'cpu[^0-9]*([\d.]+)\s*%', r'cpu[_ ]usage[^\d]*([\d.]+)'):
        m = re.search(pat, text, re.I)
        if m:
            metrics.setdefault("cpu", float(m.group(1)))
            break

    for pat in (r'mem(?:ory)?[^0-9]*([\d.]+)\s*%', r'mem(?:ory)?[_ ]usage[^\d]*([\d.]+)'):
        m = re.search(pat, text, re.I)
        if m:
            metrics.setdefault("memory", float(m.group(1)))
            break

    for pat in (r'disk[^0-9]*([\d.]+)\s*%', r'disk[_ ](?:usage|full)[^\d]*([\d.]+)'):
        m = re.search(pat, text, re.I)
        if m:
            metrics.setdefault("disk", float(m.group(1)))
            break

    # Fallback: alert is firing for a known category but no value was parsed
    if "cpu" in text and "cpu" not in metrics:
        metrics["cpu"] = 90.0
    if ("memory" in text or "mem" in text) and "memory" not in metrics:
        metrics["memory"] = 90.0
    if "disk" in text and "disk" not in metrics:
        metrics["disk"] = 90.0

    return metrics


# ── Shared DB write + anomaly pipeline ────────────────────────────────────────

async def _ingest_metrics(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    org_id: str,
    agent: Agent,
    cpu: float,
    memory: float,
    disk: float,
    net_in: int = 0,
    net_out: int = 0,
    extra: dict | None = None,
) -> None:
    """Write MetricSnapshot, run anomaly checks, schedule AI analysis."""
    from app.api.runtime import (_AGENT_EXEC_MODE, _check_anomalies,
                                 _detect_correlated_spike, _lc_analyze)

    _AGENT_EXEC_MODE.setdefault(agent.id, agent.execution_mode or "manual_approval")

    # Assign a new dict — SQLAlchemy won't detect in-place mutation of JSON
    agent.platform_info = {
        **(agent.platform_info or {}),
        "last_cpu": cpu,
        "last_memory": memory,
        "last_disk": disk,
    }

    snap = MetricSnapshot(
        org_id=org_id,
        agent_id=agent.id,
        timestamp=_now(),
        cpu=cpu,
        memory=memory,
        disk=disk,
        network_in=net_in,
        network_out=net_out,
        extra=extra or {},
    )
    db.add(snap)
    await db.commit()

    created_alerts, _resolved, _notify = await _check_anomalies(
        db, org_id, agent.id, cpu, memory, disk
    )
    if created_alerts:
        await db.flush()
        for a in created_alerts:
            db.expunge(a)
    await db.commit()

    for a in created_alerts:
        background_tasks.add_task(_lc_analyze, a, cpu, memory, org_id)

    # Cross-server correlation — auto-create SEV-2 when 3+ agents spike together
    await _detect_correlated_spike(db, org_id, agent.id, cpu, memory, disk, background_tasks)


# ── Router ────────────────────────────────────────────────────────────────────

def build_prometheus_router() -> APIRouter:
    router = APIRouter()

    # ── Thing 1: Alertmanager webhook ─────────────────────────────────────────

    @router.post("/ingest/prometheus/alertmanager")
    async def alertmanager_webhook(
        body: dict,
        background_tasks: BackgroundTasks,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        """Receive Prometheus Alertmanager webhook payloads."""
        await _check_prom_auth(request)

        firing = [a for a in body.get("alerts", []) if a.get("status", "firing") == "firing"]
        if not firing:
            return {"ok": True, "agents_notified": 0}

        org_id = request.query_params.get("org_id") or await _get_default_org_id(db)
        agents_notified = 0

        for raw_alert in firing:
            labels = raw_alert.get("labels", {})
            annotations = raw_alert.get("annotations", {})

            # Derive instance — strip :port suffix
            instance = (
                labels.get("instance")
                or labels.get("host")
                or labels.get("job")
                or "unknown"
            )
            if ":" in instance:
                instance = instance.rsplit(":", 1)[0]

            alertname = labels.get("alertname", "")
            description = (
                annotations.get("description", "")
                + " "
                + annotations.get("summary", "")
            )
            metrics = _parse_alert_text(alertname, description)
            cpu = metrics.get("cpu", 0.0)
            memory = metrics.get("memory", 0.0)
            disk = metrics.get("disk", 0.0)

            agent = await _get_or_create_prometheus_agent(db, org_id, instance)
            await _ingest_metrics(
                db, background_tasks, org_id, agent, cpu, memory, disk,
                extra={"source": "prometheus_alertmanager", "alertname": alertname},
            )
            agents_notified += 1

        return {"ok": True, "agents_notified": agents_notified}

    # ── Thing 2: Prometheus text-format scrape push ────────────────────────────

    @router.post("/ingest/prometheus/metrics")
    async def prometheus_metrics_push(
        request: Request,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        """Receive raw Prometheus exposition text (node_exporter output)."""
        await _check_prom_auth(request)

        instance = (
            request.query_params.get("instance")
            or request.query_params.get("job")
            or "unknown"
        )
        org_id = request.query_params.get("org_id") or await _get_default_org_id(db)

        raw = (await request.body()).decode("utf-8", errors="replace")
        if not raw.strip():
            raise HTTPException(status_code=400, detail="Empty body")

        m = _parse_prometheus_text(raw, instance)
        cpu = float(m.get("cpu", 0.0))
        memory = float(m.get("memory", 0.0))
        disk = float(m.get("disk", 0.0))
        net_in = int(m.get("network_in", 0))
        net_out = int(m.get("network_out", 0))

        agent = await _get_or_create_prometheus_agent(db, org_id, instance)
        await _ingest_metrics(
            db, background_tasks, org_id, agent, cpu, memory, disk, net_in, net_out,
            extra={"source": "prometheus_scrape", "instance": instance},
        )

        return {
            "ok": True,
            "instance": instance,
            "agent_id": agent.id,
            "metrics": {"cpu": cpu, "memory": memory, "disk": disk},
        }

    # ── Thing 4: Grafana alerting webhook ─────────────────────────────────────

    @router.post("/ingest/grafana/alert")
    async def grafana_alert_webhook(
        body: dict,
        background_tasks: BackgroundTasks,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        """Receive Grafana alerting webhook (unified alerting or legacy)."""
        await _check_prom_auth(request)

        state = body.get("state") or body.get("status") or "alerting"
        if state not in ("alerting", "firing", "no_data"):
            return {"ok": True, "agents_notified": 0}  # resolved — ignore

        tags = body.get("tags") or {}
        instance = (
            tags.get("instance")
            or tags.get("host")
            or body.get("ruleName", "")
            or "unknown"
        )

        eval_matches = body.get("evalMatches", [])
        title = body.get("title") or body.get("ruleName") or ""
        message = body.get("message", "")

        # Prefer structured evalMatches values
        metrics: dict[str, float] = {}
        for em in eval_matches:
            metric_name = (em.get("metric") or "").lower()
            value = em.get("value")
            if value is None:
                continue
            if "cpu" in metric_name:
                metrics.setdefault("cpu", float(value))
            elif "mem" in metric_name:
                metrics.setdefault("memory", float(value))
            elif "disk" in metric_name:
                metrics.setdefault("disk", float(value))

        if not metrics:
            metrics = _parse_alert_text(title, message)

        cpu = metrics.get("cpu", 0.0)
        memory = metrics.get("memory", 0.0)
        disk = metrics.get("disk", 0.0)

        org_id = request.query_params.get("org_id") or await _get_default_org_id(db)
        agent = await _get_or_create_prometheus_agent(db, org_id, instance)
        await _ingest_metrics(
            db, background_tasks, org_id, agent, cpu, memory, disk,
            extra={"source": "grafana_alert", "title": title},
        )

        return {"ok": True, "instance": instance, "agents_notified": 1}

    return router
