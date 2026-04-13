"""evaluator.py — Post-remediation evaluation agent.

Assesses correctness of diagnosis and effectiveness of actions using
rule-based heuristics.  Optionally can be extended with LLM evaluation.
"""
import logging
from typing import Any

from config import Config

log = logging.getLogger(__name__)

# Keywords that should appear in root_cause when the alert name contains them.
_DIAGNOSIS_KEYWORDS: dict[str, list[str]] = {
    "cpu":       ["cpu", "processor", "compute", "load"],
    "memory":    ["memory", "mem", "heap", "oom", "leak"],
    "disk":      ["disk", "storage", "filesystem", "inode", "space"],
    "latency":   ["latency", "slow", "timeout", "response time"],
    "error":     ["error", "failure", "exception", "crash", "fault"],
    "http":      ["http", "request", "endpoint", "api", "5xx"],
    "auth":      ["auth", "authentication", "token", "credential", "permission"],
}


def evaluate(
    cfg: Config,
    alert: dict,
    plan: dict,
    results: list[dict],
    store: Any,
) -> dict:
    """Rule-based evaluation of a completed remediation cycle.

    Returns:
        {
          "diagnosis_correct": bool,
          "action_effectiveness": float,   # 0.0 – 1.0
          "improvement_suggestions": [str],
        }
    """
    alert_name = alert.get("labels", {}).get("alertname", "").lower()
    root_cause = plan.get("root_cause", "").lower()

    # ── 1. Diagnosis correctness ─────────────────────────────────────────────
    diagnosis_correct = _assess_diagnosis(alert_name, root_cause)

    # ── 2. Action effectiveness ──────────────────────────────────────────────
    # Count actionable results (exclude meta-entries like "verify" / "rollback").
    real_results = [
        r for r in results
        if r.get("action") not in ("verify", "rollback") and "action" in r
    ]
    ok_count = sum(1 for r in real_results if r.get("status") in ("ok", "dry_run"))
    total = len(real_results)
    effectiveness = round(ok_count / total, 2) if total else 0.0

    # ── 3. Improvement suggestions ───────────────────────────────────────────
    suggestions: list[str] = []

    # Blocked by criticality
    blocked = [r for r in results if r.get("status") == "blocked_by_criticality"]
    if blocked:
        actions = [b["action"] for b in blocked]
        suggestions.append(
            f"Actions blocked by criticality guard: {actions}. "
            "Consider updating service criticality config or using a safer alternative."
        )

    # Rollbacks triggered
    rollbacks = [r for r in results if r.get("action") == "rollback"]
    if rollbacks:
        originals = [r.get("original_action", "?") for r in rollbacks]
        suggestions.append(
            f"Rollback triggered after: {originals}. "
            "These actions worsened metrics — review their safety for this alert type."
        )

    # Not resolved
    resolved = any(r.get("status") == "resolved" for r in results)
    if not resolved and total > 0:
        suggestions.append(
            "Issue was not resolved after all remediation stages. "
            "Consider escalating or adding more aggressive steps."
        )

    # Low confidence
    if plan.get("confidence", 1.0) < 0.7:
        suggestions.append(
            f"LLM confidence was low ({plan.get('confidence', 0):.2f}). "
            "Enrich Prometheus metrics or add application-level observability."
        )

    # Wrong diagnosis signal
    if not diagnosis_correct:
        suggestions.append(
            "Root cause description may not match the alert type. "
            "Review LLM system prompt or add more context to the alert labels."
        )

    # Historical failure rate for executed actions
    intel = store._intel.get(alert.get("labels", {}).get("alertname", ""))
    if intel:
        for r in real_results:
            action = r.get("action", "")
            stats = intel.action_stats.get(action, {})
            fail = stats.get("fail", 0)
            if fail > 3:
                suggestions.append(
                    f"Action '{action}' has {fail} historical failures. "
                    "Consider replacing it with a proven alternative."
                )

    eval_result = {
        "diagnosis_correct": diagnosis_correct,
        "action_effectiveness": effectiveness,
        "improvement_suggestions": suggestions,
    }

    log.info(
        "Evaluation | diagnosis_correct=%s effectiveness=%.2f suggestions=%d",
        diagnosis_correct, effectiveness, len(suggestions),
    )
    return eval_result


def _assess_diagnosis(alert_name: str, root_cause: str) -> bool:
    """Return True if the root_cause mentions keywords expected for this alert type."""
    for domain, keywords in _DIAGNOSIS_KEYWORDS.items():
        if domain in alert_name:
            return any(kw in root_cause for kw in keywords)
    # No domain match — can't assess; assume correct
    return True
