"""
Datadog webhook adapter for Resilo.

Receives Datadog alerts via webhook, validates signature, normalizes to Resilo format,
looks up agent by hostname, and feeds into the remediation pipeline.
"""
import hashlib
import hmac
import json
import logging
import os
import re
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select, text

from app.agents.langchain_agent import analyze_alert
from app.core.database import Agent, AlertRecord, Organization, RemediationJob, SessionLocal

logger = logging.getLogger("datadog_webhook")

router = APIRouter(prefix="/integrations/datadog", tags=["integrations"])

DATADOG_WEBHOOK_SECRET = os.getenv("DATADOG_WEBHOOK_SECRET", "")


def _validate_datadog_signature(
    body: str,
    signature: Optional[str],
) -> bool:
    """Validate Datadog webhook signature using HMAC-SHA256.
    
    If no secret is configured, log a warning but accept the request (for local testing).
    """
    if not DATADOG_WEBHOOK_SECRET:
        logger.warning("[DATADOG] No DATADOG_WEBHOOK_SECRET configured — accepting request without validation")
        return True
    
    if not signature:
        logger.warning("[DATADOG] No X-Datadog-Signature header present")
        return False
    
    # Datadog signature format: sha256=<hex>
    if not signature.startswith("sha256="):
        logger.warning("[DATADOG] Invalid signature format: %s", signature)
        return False
    
    expected_sig = signature[7:]  # Remove "sha256=" prefix
    computed = hmac.new(
        DATADOG_WEBHOOK_SECRET.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()
    
    if not hmac.compare_digest(computed, expected_sig):
        logger.warning("[DATADOG] Signature mismatch")
        return False
    
    logger.debug("[DATADOG] Signature validated")
    return True


def _parse_datadog_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize Datadog webhook payload to Resilo format.
    
    Returns:
    {
        "host": "hostname",
        "alert_type": "error|warning|info|recovery",
        "severity": "critical|high|medium|low",
        "title": "Alert title",
        "body": "Full alert text",
        "metric_name": "cpu|memory|disk|network|unknown",
        "metric_value": 92.5,
        "tags": {"env": "prod", "service": "api", "team": "platform"},
        "timestamp": <unix_ts>,
    }
    """
    # Datadog sends nested alert data in different formats.
    # Try to extract from common structures.
    
    alert = payload.get("alert", {})
    if isinstance(alert, str):
        try:
            alert = json.loads(alert)
        except:
            alert = {}
    
    host = payload.get("host", "unknown")
    title = payload.get("title", "")
    body = payload.get("body", payload.get("description", ""))
    
    # Map Datadog alert_type to severity
    alert_type = payload.get("alert_type", "info").lower()
    severity_map = {
        "error": "critical",
        "warning": "high",
        "info": "medium",
        "success": "low",
        "recovery": "resolved",
    }
    severity = severity_map.get(alert_type, "medium")
    
    # Extract tags (Datadog format: list of "key:value" strings)
    tags_raw = payload.get("tags", [])
    tags = {}
    if isinstance(tags_raw, list):
        for tag in tags_raw:
            if ":" in tag:
                k, v = tag.split(":", 1)
                if k in ("env", "service", "team", "component", "owner"):
                    tags[k] = v
    elif isinstance(tags_raw, dict):
        tags = {k: v for k, v in tags_raw.items() if k in ("env", "service", "team", "component", "owner")}
    
    # Infer metric_name from title and body keywords
    metric_name = "unknown"
    combined_text = (title + " " + body).lower()
    if any(w in combined_text for w in ("cpu", "processor", "load")):
        metric_name = "cpu"
    elif any(w in combined_text for w in ("memory", "ram", "heap")):
        metric_name = "memory"
    elif any(w in combined_text for w in ("disk", "storage", "inode")):
        metric_name = "disk"
    elif any(w in combined_text for w in ("network", "bandwidth", "latency")):
        metric_name = "network"
    
    # Try to extract numeric metric value from body
    metric_value = None
    if metric_name != "unknown":
        # Look for pattern like "92.5%" or "92.5"
        pattern = r"(\d+\.?\d*)\s*%?"
        match = re.search(pattern, body)
        if match:
            try:
                metric_value = float(match.group(1))
            except:
                pass
    
    timestamp = payload.get("timestamp", int(__import__("time").time()))
    
    return {
        "host": host,
        "alert_type": alert_type,
        "severity": severity,
        "title": title,
        "body": body,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "tags": tags,
        "timestamp": timestamp,
    }


async def _lookup_agent(
    hostname: str,
) -> Optional[Agent]:
    """Look up an agent by hostname.
    
    First try exact match on platform_info.hostname,
    then try LIKE match as fallback.
    """
    async with SessionLocal() as db:
        # Try exact match
        # Note: platform_info is JSON, so we query with ->> operator
        result = await db.execute(
            select(Agent).where(text("platform_info->>'hostname' = :hostname")).params(hostname=hostname)
        )
        agent = result.scalar_one_or_none()
        if agent:
            return agent
        
        # Try LIKE match
        # This is a fallback for short hostnames or when Datadog sends FQDN
        result = await db.execute(
            select(Agent).where(text("platform_info->>'hostname' ILIKE :hostname_pattern")).params(
                hostname_pattern=f"%{hostname}%"
            )
        )
        agent = result.scalar_one_or_none()
        return agent


async def _resolve_org_id(agent: Optional[Agent]) -> str:
    """Return a valid org id for alert/job persistence."""
    if agent and agent.org_id:
        return agent.org_id

    env_org_id = os.getenv("RESILO_ORG_ID", "").strip()
    if env_org_id:
        return env_org_id

    async with SessionLocal() as db:
        result = await db.execute(select(Organization.id).order_by(Organization.created_at.asc()).limit(1))
        existing_org_id = result.scalar_one_or_none()
        if existing_org_id:
            return existing_org_id

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No organization available for Datadog alert persistence")


@router.post("/webhook")
async def datadog_webhook(
    request_body: dict[str, Any],
    x_datadog_signature: Optional[str] = Header(None),
) -> dict[str, Any]:
    """
    POST /integrations/datadog/webhook
    
    Receives Datadog alerts, validates signature, normalizes to Resilo format,
    looks up agent by hostname, and feeds into the remediation pipeline.
    
    Returns: { received: true, alert_id, agent_id, action, confidence }
    """
    # Get raw body for signature validation (FastAPI has already parsed, so reconstruct)
    raw_body = json.dumps(request_body)
    
    if not _validate_datadog_signature(raw_body, x_datadog_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Datadog signature",
        )
    
    logger.info("[DATADOG] Received webhook: %s", request_body.get("title", "unknown"))
    
    # Parse and normalize payload
    normalized = _parse_datadog_payload(request_body)
    host = normalized["host"]
    alert_type = normalized["alert_type"]
    severity = normalized["severity"]
    metric_name = normalized["metric_name"]
    metric_value = normalized["metric_value"]
    
    logger.info(
        "[DATADOG] Normalized: host=%s metric=%s severity=%s type=%s value=%s",
        host, metric_name, severity, alert_type, metric_value,
    )
    
    # Handle recovery alerts separately
    if alert_type == "recovery":
        logger.info("[DATADOG] Recovery alert received for %s — marking as resolved", host)
        # TODO: implement resolution path if needed
        return {
            "received": True,
            "alert_id": None,
            "agent_id": None,
            "action": "resolve",
            "confidence": 1.0,
        }
    
    # Look up agent
    agent = await _lookup_agent(host)
    org_id = await _resolve_org_id(agent)
    if not agent:
        logger.warning(
            "[DATADOG] No agent found for hostname '%s' — creating unassigned alert in org '%s'",
            host, org_id,
        )
        agent_id = None
        execution_mode = "manual_approval"
    else:
        agent_id = agent.id
        execution_mode = getattr(agent, "execution_mode", "manual_approval") or "manual_approval"
        logger.info("[DATADOG] Found agent %s for hostname %s", agent_id, host)
    
    # Build metrics dict for analyze_alert
    metrics: dict[str, Any] = {"cpu": 0.0, "memory": 0.0, "disk": 0.0}
    if metric_name == "cpu" and metric_value is not None:
        metrics["cpu"] = metric_value
    elif metric_name == "memory" and metric_value is not None:
        metrics["memory"] = metric_value
    elif metric_name == "disk" and metric_value is not None:
        metrics["disk"] = metric_value
    
    # Build alert data for analyze_alert
    alert_data: dict[str, Any] = {
        "category": metric_name,
        "severity": severity,
        "agent_id": agent_id,
        "source": "datadog",
        "title": normalized["title"],
        "host": host,
        "tags": normalized["tags"],
    }
    
    # Feed into analyze_alert
    decision = await analyze_alert(
        alert_data=alert_data,
        metrics=metrics,
        top_processes=None,  # Datadog doesn't provide process info
        execution_mode=execution_mode,
    )
    
    logger.info(
        "[DATADOG] Analyzed alert: action=%s conf=%.2f target=%s",
        decision.get("action"),
        decision.get("confidence"),
        decision.get("target"),
    )
    
    # Create alert record
    async with SessionLocal() as db:
        alert_record = AlertRecord(
            org_id=org_id,
            agent_id=agent_id,
            category=metric_name,
            severity=severity,
            title=normalized["title"],
            detail=normalized["body"],
            metric_value=metric_value,
            status="open",
        )
        db.add(alert_record)
        await db.flush()
        alert_id = alert_record.id
        await db.commit()
    
    # Create remediation job if action is not notify_only
    job_id = None
    if decision.get("action") and decision.get("action") != "notify_only" and decision.get("action") != "noop":
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
                    "source": "datadog",
                },
                execution_mode=execution_mode,
                decision_source="datadog_webhook",
            )
            db.add(job)
            await db.flush()
            job_id = job.id
            await db.commit()
        
        logger.info("[DATADOG] Created remediation job %s for action %s", job_id, decision.get("action"))
    
    return {
        "received": True,
        "alert_id": alert_id,
        "agent_id": agent_id,
        "action": decision.get("action"),
        "confidence": decision.get("confidence"),
        "job_id": job_id,
    }
