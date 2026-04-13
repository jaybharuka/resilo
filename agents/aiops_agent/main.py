import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from analyzer import analyze_alert, build_explanation, reorder_steps
from config import load_config
from correlator import correlate_alerts
from detector import classify_alert_trend, fetch_alerts
from evaluator import evaluate
from remediator import execute_plan
from store import IncidentRecord, IncidentStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

cfg   = load_config()
store = IncidentStore()

_last_run: str | None  = None
_last_alert_count: int = 0
_loop_running: bool    = False


def _build_intel_context(alert_name: str) -> dict | None:
    """Construct historical intelligence context for the LLM.

    Returns None when no history exists so the LLM isn't confused by empty data.
    """
    intel = store._intel.get(alert_name)
    if not intel or not intel.action_stats:
        return None

    # Actions with > 2 historical failures
    repeat_failures = [
        a for a, s in intel.action_stats.items() if s["fail"] > 2
    ]
    best = store.get_best_actions(alert_name)

    return {
        "historical_success": best[:3],          # top 3 historically effective actions
        "historical_failures": repeat_failures,   # repeatedly failing actions to avoid
        "avg_resolution_time_seconds": round(intel.avg_resolution_time, 1),
        "last_successful_action": intel.last_successful_action,
        "effectiveness_score": round(intel.effectiveness_score, 2),
    }


async def _process_alert(alert: dict, correlation: dict | None = None) -> None:
    fp       = alert.get("fingerprint", "unknown")
    name     = alert.get("labels", {}).get("alertname", fp)
    severity = alert.get("labels", {}).get("severity", "unknown")
    instance = alert.get("labels", {}).get("instance", "")

    # ── Deduplication / attempt guard ───────────────────────────────────────
    if store.is_active(fp):
        log.debug("Skipping %s — already in-flight", name)
        return

    if store.attempt_count(fp) >= cfg.max_remediation_attempts:
        log.warning("Skipping %s — max attempts (%d) reached", name, cfg.max_remediation_attempts)
        store.record(IncidentRecord(
            fingerprint=fp, alert_name=name, severity=severity,
            root_cause="", confidence=0.0, impact="unknown",
            remediation_results=[], status="FAILED",
            skipped_reason="max_attempts_reached",
        ))
        return

    store.mark_active(fp)
    start_ts = datetime.now(timezone.utc).timestamp()

    try:
        # ── Time-aware trend classification ──────────────────────────────────
        # Replaces simple is_transient_spike — also catches gradual_increase.
        if instance:
            trend = await classify_alert_trend(cfg, alert)
            if trend == "transient_spike":
                log.info("Skipping %s — transient spike (already resolved)", name)
                store.record(IncidentRecord(
                    fingerprint=fp, alert_name=name, severity=severity,
                    root_cause="transient_spike", confidence=0.0, impact="unknown",
                    remediation_results=[], status="SKIPPED",
                    skipped_reason="transient_spike",
                ))
                return
            if trend == "unknown":
                log.debug("Alert %s trend unknown — proceeding with analysis", name)
            # "sustained_issue" and "gradual_increase" both fall through to remediation

        # ── Build LLM context: history + correlation ──────────────────────────
        intel_context = _build_intel_context(name)

        # Merge correlation data if available
        if correlation and correlation.get("correlated"):
            merged = dict(intel_context) if intel_context else {}
            merged["correlation"] = correlation
            intel_context = merged

            # Record this pattern in learning store
            if correlation.get("pattern"):
                store.record_correlation(name, correlation["pattern"])

        # ── LLM analysis ─────────────────────────────────────────────────────
        plan = await analyze_alert(cfg, alert, intel_context=intel_context)
        confidence: float = plan.get("confidence", 0.0)

        # ── Safety gates ─────────────────────────────────────────────────────
        if confidence < cfg.confidence_threshold:
            log.warning(
                "Skipping %s — confidence %.2f below threshold %.2f",
                name, confidence, cfg.confidence_threshold,
            )
            store.record(IncidentRecord(
                fingerprint=fp, alert_name=name, severity=severity,
                root_cause=plan.get("root_cause", ""), confidence=confidence,
                impact=plan.get("impact", "unknown"), remediation_results=[],
                status="SKIPPED",
                skipped_reason=f"confidence={confidence:.2f}<{cfg.confidence_threshold}",
            ))
            return

        if plan.get("escalate"):
            reason = plan.get("escalation_reason", "")
            log.warning("ESCALATE %s — %s", name, reason)
            store.record(IncidentRecord(
                fingerprint=fp, alert_name=name, severity=severity,
                root_cause=plan.get("root_cause", ""), confidence=confidence,
                impact=plan.get("impact", "unknown"), remediation_results=[],
                escalated=True, status="SKIPPED",
                skipped_reason=f"escalate: {reason}",
            ))
            return

        # ── Learning: reorder steps by history + cost ────────────────────────
        plan = reorder_steps(plan, name, store)

        # ── Multi-stage execution ─────────────────────────────────────────────
        results = await execute_plan(cfg, alert, plan, store)

        # ── Post-execution: outcome + explainability + evaluation ─────────────
        resolved = any(r.get("status") == "resolved" for r in results)
        resolution_time = (
            datetime.now(timezone.utc).timestamp() - start_ts if resolved else None
        )
        actions_executed = [
            r["action"]
            for r in results
            if "action" in r and r.get("action") not in ("verify", "rollback")
        ]

        explanation = build_explanation(plan, name, results, store, cfg)
        evaluation  = evaluate(cfg, alert, plan, results, store)

        store.record(IncidentRecord(
            fingerprint=fp, alert_name=name, severity=severity,
            root_cause=plan.get("root_cause", ""), confidence=confidence,
            impact=plan.get("impact", "unknown"), remediation_results=results,
            status="RESOLVED" if resolved else "FAILED",
            resolution_time=resolution_time,
            actions_executed=actions_executed,
            explanation=explanation,
            evaluation=evaluation,
        ))

    finally:
        store.mark_inactive(fp)


async def _poll_loop() -> None:
    global _last_run, _last_alert_count, _loop_running
    while True:
        _loop_running = True
        try:
            alerts = await fetch_alerts(cfg)
            _last_alert_count = len(alerts)
            _last_run = datetime.now(timezone.utc).isoformat()

            # Compute cross-alert correlation once per cycle for the whole batch.
            correlation = correlate_alerts(alerts) if len(alerts) > 1 else None

            for alert in alerts:
                try:
                    await _process_alert(alert, correlation=correlation)
                except Exception as exc:
                    log.error(
                        "Error processing alert %s: %s",
                        alert.get("labels", {}).get("alertname", "?"), exc,
                    )
        except Exception as exc:
            log.error("Poll loop error: %s", exc)
        finally:
            _loop_running = False

        await asyncio.sleep(cfg.poll_interval)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    task = asyncio.create_task(_poll_loop())
    log.info(
        "AIOps Agent started | model=%s dry_run=%s poll=%ds confidence_threshold=%.2f",
        cfg.llm_model, cfg.dry_run, cfg.poll_interval, cfg.confidence_threshold,
    )
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="AIOps Agent", version="0.4.0", lifespan=_lifespan)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "aiops-agent",
        "version": "0.4.0",
        "dry_run": cfg.dry_run,
        "model": cfg.llm_model,
    }


@app.post("/agent/run")
async def agent_run() -> dict:
    """Trigger an immediate detect → analyze → remediate cycle."""
    try:
        alerts = await fetch_alerts(cfg)
        correlation = correlate_alerts(alerts) if len(alerts) > 1 else None
        processed = 0
        for alert in alerts:
            try:
                await _process_alert(alert, correlation=correlation)
                processed += 1
            except Exception as exc:
                log.error("Manual run error for alert: %s", exc)
        return {"ok": True, "alerts_processed": processed}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/agent/status")
async def agent_status() -> dict:
    return {
        "loop_running": _loop_running,
        "last_run": _last_run,
        "last_alert_count": _last_alert_count,
        "poll_interval_seconds": cfg.poll_interval,
        "dry_run": cfg.dry_run,
        "model": cfg.llm_model,
        "confidence_threshold": cfg.confidence_threshold,
        **store.status(),
        "intelligence": store.intelligence(),
    }


@app.get("/agent/history")
async def agent_history(limit: int = 50) -> dict:
    """Return incident history with explanation and evaluation fields."""
    return {"history": store.history(min(limit, 200))}
