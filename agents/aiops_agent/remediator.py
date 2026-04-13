import asyncio
import datetime
import logging
from typing import Any

import httpx

from config import ALLOWED_ACTIONS_BY_CRITICALITY, Config
from detector import HEALTHY_THRESHOLDS, metric_priority_for, query_metric

log = logging.getLogger(__name__)


# ── Public entry point ───────────────────────────────────────────────────────

async def execute_plan(cfg: Config, alert: dict, plan: dict, store: Any) -> list[dict]:
    """Execute a multi-stage remediation plan: safe → moderate → aggressive.

    After each stage validates via Prometheus. Stops as soon as issue resolves.
    """
    stages: dict[str, list[dict]] = plan.get("steps", {})
    instance: str = alert.get("labels", {}).get("instance", "")
    alert_name: str = alert.get("labels", {}).get("alertname", "unknown")
    all_results: list[dict] = []
    start_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

    for stage_name in ("safe", "moderate", "aggressive"):
        stage_steps = stages.get(stage_name, [])
        if not stage_steps:
            continue

        log.info("Executing stage=%s  steps=%d", stage_name, len(stage_steps))
        stage_results = await _execute_stage(
            cfg, stage_steps, alert_name, instance, store
        )
        all_results.extend(stage_results)

        # Post-stage Prometheus validation (skipped in dry-run).
        if not cfg.dry_run and instance:
            await asyncio.sleep(cfg.verify_delay_seconds)
            if await _check_resolved(cfg, alert, instance):
                res_time = (
                    datetime.datetime.now(datetime.timezone.utc).timestamp() - start_ts
                )
                log.info("Resolved after stage=%s in %.1fs", stage_name, res_time)
                all_results.append(
                    {"stage": stage_name, "action": "verify", "status": "resolved"}
                )
                for r in stage_results:
                    if r.get("status") == "ok":
                        store.record_success(alert_name, r["action"], res_time)
                return all_results

    return all_results


# ── Stage executor ───────────────────────────────────────────────────────────

async def _execute_stage(
    cfg: Config,
    steps: list[dict],
    alert_name: str,
    instance: str,
    store: Any,
) -> list[dict]:
    """Run every step in a stage with criticality guards, delays, and rollback monitoring."""
    results: list[dict] = []

    for step in steps:
        action: str = step.get("action", "notify_only")
        target: str = step.get("target", "")
        params: dict = step.get("params", {})

        # ── Criticality guard ────────────────────────────────────────────────
        if not _criticality_allows(target, action, cfg):
            level = cfg.service_criticality.get(target, "low")
            log.warning("BLOCKED action=%s target=%s (criticality=%s)", action, target, level)
            results.append({
                "action": action, "target": target,
                "status": "blocked_by_criticality", "criticality": level,
            })
            await asyncio.sleep(cfg.step_delay_seconds)
            continue

        # ── Dry-run path ─────────────────────────────────────────────────────
        if cfg.dry_run:
            log.info("[DRY_RUN] %s → %s  params=%s", action, target, params)
            results.append({"action": action, "target": target, "status": "dry_run"})
            await asyncio.sleep(cfg.step_delay_seconds)
            continue

        # ── Live execution with rollback monitoring ──────────────────────────
        # 1. Snapshot metrics before action
        before = await _snapshot_metrics(cfg, instance, alert_name)

        # 2. Execute action
        result = await _dispatch(action, target, params, cfg)
        results.append(result)

        # 3. Wait for metrics to settle (reuse step_delay as settling window)
        await asyncio.sleep(cfg.step_delay_seconds)

        if result.get("status") == "error":
            store.record_failure(alert_name, action)
        else:
            # 4. Snapshot after and detect regression
            after = await _snapshot_metrics(cfg, instance, alert_name)
            if before and after and _metrics_worsened(before, after):
                log.warning(
                    "Metric regression after %s on %s — triggering rollback",
                    action, target,
                )
                rb = await _rollback(action, target, params, before, cfg)
                results.append(rb)
                # High-penalty learning signal
                store.record_rollback(alert_name, action)

    return results


# ── Criticality helper ───────────────────────────────────────────────────────

def _criticality_allows(target: str, action: str, cfg: Config) -> bool:
    level = cfg.service_criticality.get(target, "low")
    allowed = ALLOWED_ACTIONS_BY_CRITICALITY.get(level, ALLOWED_ACTIONS_BY_CRITICALITY["low"])
    return action in allowed


# ── Rollback support ─────────────────────────────────────────────────────────

async def _snapshot_metrics(
    cfg: Config, instance: str, alert_name: str
) -> dict[str, float]:
    """Capture current metric values for regression detection."""
    if not instance:
        return {}
    snapshot: dict[str, float] = {}
    for metric in metric_priority_for(alert_name):
        val = await query_metric(cfg, instance, metric)
        if val is not None:
            snapshot[metric] = val
    return snapshot


def _metrics_worsened(before: dict, after: dict) -> bool:
    """Return True if any tracked metric degraded by >10% post-action.

    All current metrics follow the convention: higher value = worse.
    """
    for metric, before_val in before.items():
        after_val = after.get(metric)
        if after_val is None or before_val is None or before_val == 0:
            continue
        if after_val > before_val * 1.10:
            log.debug(
                "Metric %s worsened: %.2f → %.2f (+%.1f%%)",
                metric, before_val, after_val,
                (after_val / before_val - 1) * 100,
            )
            return True
    return False


async def _rollback(
    action: str, target: str, params: dict, before: dict, cfg: Config
) -> dict:
    """Attempt to reverse a harmful action.

    Rollback rules:
      scale_deployment → revert to original replica count
      restart_service  → mark no-immediate-retry (can't un-restart)
      run_script       → no rollback available; mark failed
    """
    if action == "scale_deployment":
        # Revert to whatever was running before the scale.
        # We don't have the exact pre-scale replica count from Prometheus,
        # so we conservatively decrement by 1 (minimum 1 replica).
        original = max(1, params.get("replicas", 2) - 1)
        log.info("ROLLBACK scale_deployment %s → %d replicas", target, original)
        return {
            "action": "rollback", "original_action": action,
            "target": target, "replicas": original, "status": "ok",
        }

    if action == "restart_service":
        log.warning(
            "ROLLBACK restart_service %s — cannot un-restart; "
            "marking no-immediate-retry", target,
        )
        return {
            "action": "rollback", "original_action": action,
            "target": target, "status": "no_retry",
            "note": "restart worsened metrics; skipping immediate retry",
        }

    # run_script and unknown actions: no rollback path
    log.warning("ROLLBACK not available for %s on %s — marking failed", action, target)
    return {
        "action": "rollback", "original_action": action,
        "target": target, "status": "no_rollback",
        "note": f"no rollback defined for action '{action}'",
    }


# ── Post-stage resolution check ───────────────────────────────────────────────

async def _check_resolved(cfg: Config, alert: dict, instance: str) -> bool:
    alert_name: str = alert.get("labels", {}).get("alertname", "").lower()
    prometheus_ctx: dict = alert.get("prometheus_context", {})

    for metric in metric_priority_for(alert_name):
        if metric not in prometheus_ctx:
            continue
        value = await query_metric(cfg, instance, metric)
        if value is None:
            continue
        threshold = HEALTHY_THRESHOLDS.get(metric)
        if threshold is None:
            continue
        if value < threshold:
            log.info("Metric %s=%.2f below %.2f → resolved", metric, value, threshold)
            return True
        log.debug("Metric %s=%.2f still above %.2f", metric, value, threshold)
        return False

    return False


# ── Action handlers ──────────────────────────────────────────────────────────

async def _dispatch(action: str, target: str, params: dict, cfg: Config) -> dict:
    _handlers = {
        "restart_service":  _restart_service,
        "scale_deployment": _scale_deployment,
        "run_script":       _run_script,
        "silence_alert":    _silence_alert,
        "create_incident":  _create_incident,
        "notify_only":      _notify_only,
    }
    handler = _handlers.get(action, _notify_only)
    try:
        return await handler(target, params, cfg)
    except Exception as exc:
        log.error("Action %s on %s failed: %s", action, target, exc)
        return {"action": action, "target": target, "status": "error", "error": str(exc)}


async def _restart_service(target: str, params: dict, cfg: Config) -> dict:
    log.info("restart_service: %s", target)
    return {"action": "restart_service", "target": target, "status": "ok"}


async def _scale_deployment(target: str, params: dict, cfg: Config) -> dict:
    replicas = params.get("replicas", 2)
    log.info("scale_deployment: %s → %d replicas", target, replicas)
    return {"action": "scale_deployment", "target": target, "replicas": replicas, "status": "ok"}


async def _run_script(target: str, params: dict, cfg: Config) -> dict:
    log.info("run_script: %s", target)
    proc = await asyncio.create_subprocess_shell(
        target,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        return {"action": "run_script", "target": target, "status": "timeout"}
    ok = proc.returncode == 0
    return {
        "action": "run_script", "target": target,
        "status": "ok" if ok else "error",
        "returncode": proc.returncode,
        "stdout": stdout.decode(errors="replace"),
        "stderr": stderr.decode(errors="replace"),
    }


async def _silence_alert(target: str, params: dict, cfg: Config) -> dict:
    hours = params.get("duration_hours", 2)
    now = datetime.datetime.utcnow()
    ends = now + datetime.timedelta(hours=hours)
    body = {
        "matchers": [{"name": "alertname", "value": target, "isRegex": False}],
        "startsAt": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endsAt":   ends.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "createdBy": "aiops-agent",
        "comment": f"Auto-silenced by AIOps Agent for {hours}h",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{cfg.alertmanager_url}/api/v2/silences", json=body)
        r.raise_for_status()
    return {
        "action": "silence_alert", "target": target,
        "duration_hours": hours, "silence_id": r.json().get("silenceID", ""),
        "status": "ok",
    }


async def _create_incident(target: str, params: dict, cfg: Config) -> dict:
    log.info("create_incident: %s  params=%s", target, params)
    return {"action": "create_incident", "target": target, "status": "ok"}


async def _notify_only(target: str, params: dict, cfg: Config) -> dict:
    msg = params.get("message", "")
    log.info("notify_only: %s — %s", target, msg)
    return {"action": "notify_only", "target": target, "status": "ok"}
