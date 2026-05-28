"""
Prometheus Alertmanager webhook adapter for Resilo.

Receives Alertmanager webhooks, normalizes them to Resilo format,
looks up the target agent by hostname, and feeds the result into the
same remediation pipeline used by the Datadog adapter.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, text

from app.agents.langchain_agent import analyze_alert
from app.core.database import Agent, AlertRecord, Organization, RemediationJob, SessionLocal

logger = logging.getLogger("prometheus_webhook")

router = APIRouter(prefix="/integrations/prometheus", tags=["integrations"])


def _get_first_present(mapping: dict[str, Any], keys: list[str], default: str = "") -> str:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _normalize_label_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_metric_value(text: str) -> float | None:
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*%?", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _infer_metric_name(text: str, labels: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            text,
            " ".join(f"{k}={v}" for k, v in labels.items()),
        ]
    ).lower()
    if any(token in haystack for token in ("cpu", "load")):
        return "cpu"
    if any(token in haystack for token in ("memory", "ram", "heap")):
        return "memory"
    if any(token in haystack for token in ("disk", "filesystem", "inode", "storage")):
        return "disk"
    if any(token in haystack for token in ("network", "latency", "packet", "bandwidth")):
        return "network"
    return "unknown"


def _extract_process_name(labels: dict[str, Any], annotations: dict[str, Any], title: str, body: str) -> str | None:
    candidates = [
        labels.get("process"),
        labels.get("process_name"),
        labels.get("container"),
        labels.get("pod"),
        annotations.get("process"),
        annotations.get("process_name"),
        annotations.get("summary"),
        title,
        body,
    ]
    for candidate in candidates:
        text_value = _normalize_label_value(candidate)
        if not text_value:
            continue
        match = re.search(r"(?:process|container|pod)[:=\s]+([a-zA-Z0-9._-]+)", text_value, re.IGNORECASE)
        if match:
            return match.group(1)
        words = text_value.split()
        if len(words) == 1 and words[0].lower() not in {"cpu", "memory", "disk", "network", "alert", "warning", "critical"}:
            return words[0]
    return None


def _extract_host(alert: dict[str, Any], common_labels: dict[str, Any], group_labels: dict[str, Any]) -> str:
    labels = alert.get("labels", {}) if isinstance(alert, dict) else {}
    candidates = [
        labels.get("instance"),
        labels.get("host"),
        labels.get("hostname"),
        labels.get("node"),
        common_labels.get("instance"),
        common_labels.get("host"),
        common_labels.get("hostname"),
        group_labels.get("instance"),
        group_labels.get("host"),
        group_labels.get("hostname"),
    ]
    for candidate in candidates:
        host = _normalize_label_value(candidate)
        if host:
            return host.split(":", 1)[0]
    return "unknown"


async def _lookup_agent(hostname: str) -> Optional[Agent]:
    async with SessionLocal() as db:
        result = await db.execute(
            select(Agent).where(text("platform_info->>'hostname' = :hostname")).params(hostname=hostname)
        )
        agent = result.scalar_one_or_none()
        if agent:
            return agent

        result = await db.execute(
            select(Agent).where(text("platform_info->>'hostname' ILIKE :hostname_pattern")).params(
                hostname_pattern=f"%{hostname}%"
            )
        )
        return result.scalar_one_or_none()


async def _resolve_org_id(agent: Optional[Agent]) -> str:
    if agent and agent.org_id:
        return agent.org_id

    import os

    env_org_id = os.getenv("RESILO_ORG_ID", "").strip()
    if env_org_id:
        return env_org_id

    async with SessionLocal() as db:
        result = await db.execute(select(Organization.id).order_by(Organization.created_at.asc()).limit(1))
        org_id = result.scalar_one_or_none()
        if org_id:
            return org_id

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No organization available for Prometheus alert persistence")


async def _find_existing_alert(org_id: str, host: str, alertname: str) -> Optional[AlertRecord]:
    async with SessionLocal() as db:
        result = await db.execute(
            select(AlertRecord)
            .where(AlertRecord.org_id == org_id)
            .where(AlertRecord.status == "open")
            .where((AlertRecord.title.ilike(f"%{alertname}%")) | (AlertRecord.detail.ilike(f"%{host}%")))
            .order_by(AlertRecord.created_at.desc())
        )
        return result.scalar_one_or_none()


@router.post("/webhook")
async def prometheus_webhook(request_body: dict[str, Any]) -> dict[str, Any]:
    """POST /integrations/prometheus/webhook

    Accept Alertmanager webhooks without JWT. Authentication is handled by
    upstream routing and the Alertmanager payload itself.
    """
    status_value = str(request_body.get("status", "firing")).lower()
    alerts = request_body.get("alerts") or []
    if not isinstance(alerts, list):
        alerts = []

    group_labels = request_body.get("groupLabels") or {}
    common_labels = request_body.get("commonLabels") or {}
    common_annotations = request_body.get("commonAnnotations") or {}

    if status_value == "resolved":
        host = _extract_host(alerts[0] if alerts else {}, common_labels, group_labels)
        labels = alerts[0].get("labels", {}) if alerts and isinstance(alerts[0], dict) else {}
        alertname = _get_first_present(labels, ["alertname"], _get_first_present(common_labels, ["alertname"], "prometheus_alert"))
        agent = await _lookup_agent(host) if host != "unknown" else None
        org_id = await _resolve_org_id(agent)
        existing_alert = await _find_existing_alert(org_id, host, alertname)

        if existing_alert is not None:
            async with SessionLocal() as db:
                alert = await db.get(AlertRecord, existing_alert.id)
                if alert is not None:
                    alert.status = "resolved"
                    alert.resolved_at = datetime.now(timezone.utc)
                    db.add(alert)
                    await db.commit()

        logger.info("[PROMETHEUS] Recovery webhook received for host=%s alert=%s", host, alertname)
        return {
            "received": True,
            "alert_id": getattr(existing_alert, "id", None),
            "agent_id": None,
            "action": "resolve",
            "confidence": 1.0,
        }

    primary_alert = alerts[0] if alerts else {}
    labels = primary_alert.get("labels", {}) if isinstance(primary_alert, dict) else {}
    annotations = primary_alert.get("annotations", {}) if isinstance(primary_alert, dict) else {}

    host = _extract_host(primary_alert, common_labels, group_labels)
    alertname = _get_first_present(labels, ["alertname"], _get_first_present(common_labels, ["alertname"], "prometheus_alert"))
    title = _get_first_present(annotations, ["summary", "title"], _get_first_present(common_annotations, ["summary", "description"], alertname))
    body = _get_first_present(annotations, ["description", "message"], _get_first_present(common_annotations, ["description", "message"], title))

    labels_for_tags = {**common_labels, **labels}
    tags = {
        "env": _normalize_label_value(labels_for_tags.get("env")),
        "service": _normalize_label_value(labels_for_tags.get("service")),
        "team": _normalize_label_value(labels_for_tags.get("team")),
    }
    tags = {key: value for key, value in tags.items() if value}

    metric_name = _infer_metric_name(f"{title} {body} {alertname}", labels_for_tags)
    metric_value = _parse_metric_value(body)
    if metric_value is None:
        metric_value = _parse_metric_value(title)

    process_name = _extract_process_name(labels, annotations, title, body)

    alert_type = "warning"
    if metric_name == "cpu" and metric_value is not None and metric_value >= 90:
        alert_type = "error"
    elif metric_name == "memory" and metric_value is not None and metric_value >= 85:
        alert_type = "error"

    severity_map = {
        "error": "critical",
        "warning": "high",
        "info": "medium",
        "recovery": "resolved",
    }
    severity = severity_map.get(alert_type, "high")

    agent = await _lookup_agent(host)
    org_id = await _resolve_org_id(agent)
    if not agent:
        logger.warning("[PROMETHEUS] No agent found for hostname '%s' — creating unassigned alert in org '%s'", host, org_id)
        agent_id = None
        execution_mode = "manual_approval"
    else:
        agent_id = agent.id
        execution_mode = getattr(agent, "execution_mode", "manual_approval") or "manual_approval"
        logger.info("[PROMETHEUS] Found agent %s for host %s", agent_id, host)

    metrics: dict[str, Any] = {"cpu": 0.0, "memory": 0.0, "disk": 0.0}
    if metric_name in metrics and metric_value is not None:
        metrics[metric_name] = metric_value

    alert_data: dict[str, Any] = {
        "category": metric_name,
        "severity": severity,
        "agent_id": agent_id,
        "source": "prometheus",
        "title": title,
        "host": host,
        "tags": tags,
    }

    decision = await analyze_alert(
        alert_data=alert_data,
        metrics=metrics,
        top_processes={
            "by_cpu": (
                [{"name": process_name, "cpu_percent": metric_value or 95.0, "memory_percent": 0.0}]
                if process_name and metric_name == "cpu" and metric_value is not None
                else []
            ),
            "by_mem": (
                [{"name": process_name, "cpu_percent": 10.0, "memory_percent": metric_value or 95.0}]
                if process_name and metric_name == "memory" and metric_value is not None
                else []
            ),
        },
        execution_mode=execution_mode,
    )

    async with SessionLocal() as db:
        alert_record = AlertRecord(
            org_id=org_id,
            agent_id=agent_id,
            category=metric_name,
            severity=severity,
            title=title,
            detail=body,
            metric_value=metric_value,
            status="open",
        )
        db.add(alert_record)
        await db.flush()
        alert_id = alert_record.id
        await db.commit()

    job_id = None
    if decision.get("action") not in (None, "notify_only", "noop"):
        async with SessionLocal() as db:
            job = RemediationJob(
                org_id=org_id,
                alert_id=alert_id,
                playbook_type=decision.get("action"),
                status="pending",
                attempts=0,
                max_retries=1,
                payload={
                    "action": decision.get("action"),
                    "target": decision.get("target"),
                    "agent_id": agent_id,
                    "source": "prometheus",
                },
                execution_mode=execution_mode,
                decision_source="prometheus_webhook",
            )
            db.add(job)
            await db.flush()
            job_id = job.id
            await db.commit()

    logger.info(
        "[PROMETHEUS] Handled webhook host=%s alert=%s metric=%s action=%s conf=%.2f",
        host,
        alertname,
        metric_name,
        decision.get("action"),
        float(decision.get("confidence", 0.0)),
    )

    return {
        "received": True,
        "alert_id": alert_id,
        "agent_id": agent_id,
        "action": decision.get("action"),
        "confidence": decision.get("confidence"),
        "job_id": job_id,
    }