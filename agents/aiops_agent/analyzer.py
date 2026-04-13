import json
import logging
from typing import Any

import httpx

from config import ACTION_COST, Config

log = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert SRE analyzing production alerts.
Given alert data with enriched Prometheus metrics, respond ONLY with a valid JSON object.
No explanation, no markdown fences, no extra text — raw JSON only.

Required schema:
{
  "root_cause": "<concise technical root cause>",
  "confidence": <0.0-1.0>,
  "impact": "<low|medium|high|critical>",
  "escalate": <true|false>,
  "escalation_reason": "<why escalation is needed; empty string if escalate=false>",
  "summary": "<1-2 sentence human-readable summary>",
  "steps": {
    "safe": [
      {
        "order": <integer, 1=first>,
        "action": "notify_only|silence_alert",
        "target": "<service or alert name>",
        "params": {},
        "rationale": "<why>"
      }
    ],
    "moderate": [
      {
        "order": <integer>,
        "action": "create_incident|scale_deployment",
        "target": "<service or deployment name>",
        "params": {},
        "rationale": "<why>"
      }
    ],
    "aggressive": [
      {
        "order": <integer>,
        "action": "restart_service|run_script",
        "target": "<service name or script path>",
        "params": {},
        "rationale": "<why>"
      }
    ]
  }
}

Rules:
- safe    → non-disruptive: notify, silence
- moderate → limited impact: incidents, scaling
- aggressive → disruptive: restarts, scripts
- If escalate=true set steps={"safe":[],"moderate":[],"aggressive":[]}.
- Each stage list may be empty if that severity is not warranted.
- Confidence must reflect certainty given available metrics.
- Set escalate=true for data-loss risk, security incidents, or ambiguous root cause.
- IMPORTANT: If historical_context is provided in the alert data, prefer actions
  listed in historical_success and avoid actions listed in historical_failures
  unless you have strong reasoning to override.
"""

_SAFE_ACTIONS = frozenset({"notify_only", "silence_alert"})
_MODERATE_ACTIONS = frozenset({"create_incident", "scale_deployment"})


def _parse_json(raw: str) -> dict:
    """Extract JSON from the LLM response, tolerating accidental prose wrappers."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        log.error("LLM returned non-JSON content: %s", raw[:300])
        raise ValueError("LLM did not return valid JSON")


def _normalize_plan(plan: dict) -> dict:
    """Convert old flat remediation_steps → multi-stage steps format."""
    if "steps" in plan:
        return plan
    flat: list[dict] = plan.get("remediation_steps", [])
    safe, moderate, aggressive = [], [], []
    for step in flat:
        action = step.get("action", "")
        if action in _SAFE_ACTIONS:
            safe.append(step)
        elif action in _MODERATE_ACTIONS:
            moderate.append(step)
        else:
            aggressive.append(step)
    return {**plan, "steps": {"safe": safe, "moderate": moderate, "aggressive": aggressive}}


def reorder_steps(plan: dict, alert_name: str, store: Any) -> dict:
    """Reorder steps within each stage using history + cost.

    Sorting key (ascending = higher priority):
      1. History rank from get_best_actions (lower = historically better)
      2. ACTION_COST (lower = cheaper, prefer when success rates similar)

    Falls back to pure cost-based ordering when no history exists.
    """
    best_actions = store.get_best_actions(alert_name)

    def _key(step: dict) -> tuple[int, int]:
        action = step.get("action", "")
        cost = ACTION_COST.get(action, 0)
        if best_actions:
            try:
                rank = best_actions.index(action)
            except ValueError:
                rank = len(best_actions)
        else:
            rank = 0  # No history — differentiate only by cost
        return (rank, cost)

    stages = plan.get("steps", {})
    return {
        **plan,
        "steps": {
            stage: sorted(steps, key=_key)
            for stage, steps in stages.items()
        },
    }


def build_explanation(
    plan: dict,
    alert_name: str,
    results: list[dict],
    store: Any,
    cfg: Config,
) -> dict:
    """Build a human-readable explanation of the remediation decision.

    Draws on: LLM rationale fields, learning history, cost policy, criticality.
    """
    intel = store._intel.get(alert_name)
    all_steps = [
        step
        for stage_steps in plan.get("steps", {}).values()
        for step in stage_steps
    ]

    # Identify the first successfully executed action
    ok_results = [r for r in results if r.get("status") == "ok"]
    primary_action = ok_results[0].get("action", "none") if ok_results else "none"

    # Pull LLM rationale for the primary action
    step_meta = next(
        (s for s in all_steps if s.get("action") == primary_action), {}
    )
    rationale_parts = []
    if step_meta.get("rationale"):
        rationale_parts.append(step_meta["rationale"])

    # Append historical context if available
    if intel and primary_action in intel.action_stats:
        s = intel.action_stats[primary_action]
        rationale_parts.append(
            f"history: {s['success']} successes / {s['fail']} failures"
        )

    # Cost note
    cost = ACTION_COST.get(primary_action, 0)
    if cost > 0:
        rationale_parts.append(f"cost={cost}")

    # Alternatives that were not the primary
    alternatives = list({s.get("action") for s in all_steps} - {primary_action, ""})

    # Blocked / rejected reasons
    rejected: list[str] = []
    for r in results:
        if r.get("status") == "blocked_by_criticality":
            rejected.append(
                f"{r['action']} blocked (criticality={r.get('criticality', '?')})"
            )
    if intel:
        for action, stats in intel.action_stats.items():
            if stats["fail"] > 2 and action in alternatives:
                rejected.append(f"{action} has {stats['fail']} historical failures")

    return {
        "why_this_action": " | ".join(rationale_parts) or plan.get("summary", ""),
        "alternatives_considered": alternatives,
        "reason_for_rejection": "; ".join(rejected) if rejected else "none",
        "confidence": plan.get("confidence", 0.0),
        "action_cost": cost,
    }


async def analyze_alert(
    cfg: Config,
    alert: dict,
    intel_context: dict | None = None,
) -> dict:
    """Call NVIDIA NIM to produce a multi-stage remediation plan.

    `intel_context` is optional structured history injected into the user
    message so the LLM can make historically-informed decisions.
    """
    alert_payload = dict(alert)

    # Inject historical intelligence into the alert payload so the LLM sees it.
    if intel_context:
        alert_payload["historical_context"] = intel_context

    user_msg = f"Alert data:\n{json.dumps(alert_payload, indent=2, default=str)}"

    payload = {
        "model": cfg.llm_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            f"{cfg.nvidia_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg.nvidia_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        r.raise_for_status()

    raw: str = r.json()["choices"][0]["message"]["content"].strip()
    plan = _normalize_plan(_parse_json(raw))

    log.info(
        "Analysis complete | confidence=%.2f escalate=%s impact=%s",
        plan.get("confidence", 0.0),
        plan.get("escalate", False),
        plan.get("impact", "unknown"),
    )
    return plan
