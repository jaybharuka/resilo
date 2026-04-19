"""
LangChain-based AIOps agent for alert analysis and remediation planning.
Uses NVIDIA NIM (OpenAI-compatible) as the LLM backend.

Section 6: Direct JSON generation — no tool calls. The LLM returns a JSON
object that is parsed directly. On any failure, rule_based_fallback() is used.

Output flows back to runtime._lc_analyze which applies execution-mode guards.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("langchain_agent")

_SYSTEM_PROMPT = """\
You are an AI infrastructure operations agent. You analyze server alerts \
and decide on safe remediation actions.

You will receive:
- Current metric values (CPU%, Memory%, Disk%, Swap%, Load average)
- The top 5 processes by CPU and by Memory at the time of the alert
- The agent's execution mode: dry_run | manual_approval | auto_safe
- Historical success rate for each action type on this agent

Your response must be JSON with this exact structure:
{
  "action": "scale_memory" | "disk_cleanup" | "restart_service" | "notify_only" | "noop",
  "target": "service name if restart_service, else null",
  "reasoning": "1-2 sentences explaining your diagnosis based on the process data",
  "confidence": 0.0,
  "contributing_process": "process name if a specific process is the cause, else null"
}

Rules:
- If top process CPU > 70%, name it in contributing_process and explain it
- If action is restart_service and execution_mode is auto_safe, confidence must be > 0.75
- If you are uncertain, choose notify_only rather than a potentially harmful action
- Never recommend restarting system-critical services (sshd, postgresql, nginx, docker, systemd)
- Respond ONLY with the JSON object — no markdown, no prose, no explanation outside the JSON\
"""

_SAFE_ACTIONS: frozenset[str] = frozenset({"restart_service", "scale_memory", "disk_cleanup", "notify_only", "noop"})

PROTECTED_SERVICES: frozenset[str] = frozenset({
    "sshd", "ssh", "postgresql", "postgres", "mysql", "nginx", "apache2",
    "httpd", "docker", "containerd", "kubelet", "etcd", "kube-apiserver",
    "systemd", "init", "dbus", "NetworkManager",
})

MAX_AUTO_RESTARTS_PER_HOUR: int = 3


def can_auto_execute(
    action: str,
    target: str,
    agent_id: str,
    restart_count_last_hour: int = 0,
) -> tuple[bool, str]:
    """Return (allowed, reason). Called before queuing any auto_safe command."""
    if action not in _SAFE_ACTIONS:
        return False, f"action '{action}' not in SAFE_ACTIONS"
    if action == "restart_service":
        if target.lower() in PROTECTED_SERVICES:
            return False, f"service '{target}' is in PROTECTED_SERVICES — requires manual approval"
        if restart_count_last_hour >= MAX_AUTO_RESTARTS_PER_HOUR:
            return False, (
                f"restart rate limit reached: {restart_count_last_hour}/{MAX_AUTO_RESTARTS_PER_HOUR} "
                f"restarts in the last hour for agent {agent_id}"
            )
    return True, ""


def rule_based_fallback(alert_data: dict[str, Any]) -> dict[str, Any]:
    """Simple rule-based fallback when LLM is unavailable. confidence=0.4, source=rule_fallback."""
    category = alert_data.get("category", "")
    if category == "cpu":
        action, target = "notify_only", "high_cpu"
        reason = "CPU pressure detected — notifying operator (LLM unavailable)"
    elif category == "memory":
        action, target = "scale_memory", "system"
        reason = "Memory pressure detected — scale_memory recommended (LLM unavailable)"
    elif category == "disk":
        action, target = "disk_cleanup", "system"
        reason = "Disk pressure detected — cleanup recommended (LLM unavailable)"
    else:
        action, target = "notify_only", category
        reason = f"Alert detected: {category} (LLM unavailable — rule fallback)"
    return {
        "action": action,
        "target": target,
        "reasoning": reason,
        "confidence": 0.4,
        "contributing_process": None,
        "safe": True,
        "decision_source": "rule_fallback",
    }


async def get_action_success_rates(agent_id: str, db: Any) -> dict[str, str]:
    """Query AgentActionLog and return per-action success rates as human-readable strings."""
    from sqlalchemy import Integer, func, select
    from app.core.database import AgentActionLog

    try:
        result = await db.execute(
            select(
                AgentActionLog.action,
                func.count().label("total"),
                func.sum(func.cast(AgentActionLog.success, Integer)).label("successes"),
            )
            .where(AgentActionLog.agent_id == agent_id)
            .group_by(AgentActionLog.action)
        )
        rates: dict[str, str] = {}
        for row in result.all():
            total = row.total or 0
            successes = int(row.successes or 0)
            pct = int(successes / total * 100) if total > 0 else 0
            rates[row.action] = f"{successes}/{total} ({pct}%)"
        return rates
    except Exception as exc:
        log.warning("[AGENT] get_action_success_rates failed: %s", exc)
        return {}


async def analyze_alert(
    alert_data: dict[str, Any],
    metrics: dict[str, Any],
    success_rate: float | None = None,
    context: str = "",
    failure_streak: int = 0,
    action_rankings: list[dict] | None = None,
    top_processes: dict | None = None,
    load_avg_1m: float | None = None,
    load_avg_5m: float | None = None,
    load_avg_15m: float | None = None,
    action_success_rates: dict[str, str] | None = None,
    execution_mode: str = "dry_run",
) -> dict[str, Any]:
    """Direct JSON generation via NVIDIA NIM. Never raises — returns rule_based_fallback on failure."""
    if not os.getenv("NVIDIA_API_KEY"):
        log.warning("[AGENT] NVIDIA_API_KEY not set — using rule-based fallback")
        return rule_based_fallback(alert_data)

    tp = top_processes or {}
    by_cpu = tp.get("by_cpu", [])
    by_mem = tp.get("by_mem", [])

    def _fmt_procs(procs: list) -> str:
        if not procs:
            return "no data"
        return ", ".join(
            f"{p.get('name', '?')}({p.get('cpu_percent', 0):.1f}% cpu, {p.get('memory_percent', 0):.1f}% mem)"
            for p in procs[:5]
        )

    rates_str = json.dumps(action_success_rates or {}, ensure_ascii=False)

    user_message = (
        f"Alert: {alert_data.get('category', '')} at {metrics.get('cpu', metrics.get('memory', 0)):.1f}%"
        f" — Severity: {alert_data.get('severity', '')}\n"
        f"Agent mode: {execution_mode}\n"
        f"Metrics: CPU={metrics.get('cpu', 0):.1f}%  Memory={metrics.get('memory', 0):.1f}%"
        f"  Disk={metrics.get('disk', 0):.1f}%\n"
        f"Load average: {f'{load_avg_1m:.2f} / {load_avg_5m:.2f} / {load_avg_15m:.2f}' if load_avg_1m is not None else 'unavailable (Windows)'}\n"
        f"Top CPU processes: {_fmt_procs(by_cpu)}\n"
        f"Top Memory processes: {_fmt_procs(by_mem)}\n"
        f"Historical action success rates: {rates_str}"
    )

    log.info("[AGENT] Invoking NIM: alert=%s severity=%s mode=%s",
             alert_data.get("category"), alert_data.get("severity"), execution_mode)

    try:
        from langchain_openai import ChatOpenAI  # lazy — not all envs have langchain installed
        llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct"),
            api_key=os.getenv("NVIDIA_API_KEY", "placeholder"),
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            temperature=0.2,
            max_tokens=512,
        )
        response = await llm.ainvoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ])
        raw = response.content.strip()
        start = raw.find("{"); end = raw.rfind("}") + 1
        if start == -1:
            raise ValueError("No JSON object in LLM response")
        parsed = json.loads(raw[start:end])

        action  = parsed.get("action", "noop")
        target  = parsed.get("target") or ""
        if isinstance(target, str) and target.lower() in ("null", "none"):
            target = ""

        decision = {
            "action":               action if action in _SAFE_ACTIONS else "noop",
            "target":               target,
            "reasoning":            parsed.get("reasoning", ""),
            "confidence":           float(parsed.get("confidence", 0.7)),
            "contributing_process": parsed.get("contributing_process"),
            "safe":                 action in _SAFE_ACTIONS,
            "decision_source":      "langchain",
        }
        log.info("[AGENT PLAN] action=%s target=%s conf=%.2f contributing=%s",
                 decision["action"], target, decision["confidence"],
                 decision["contributing_process"])
        return decision

    except Exception as exc:
        log.warning("[AGENT] LangChain invoke failed: %s — falling back to rule-based", exc)
        return rule_based_fallback(alert_data)
