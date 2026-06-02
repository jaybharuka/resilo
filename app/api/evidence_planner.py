"""
evidence_planner.py — LLM-driven iterative evidence planning (Phase 5).

The planner asks the LLM: "Given what you know so far, what evidence
would you gather next?" — runs that collector — then repeats until the
LLM says it has enough to form a root cause or the budget is exhausted.

This replaces the static dispatch table in context_collector.py with an
adaptive loop that mirrors how a senior SRE investigates.

Algorithm:
  1. Build initial evidence snapshot (metrics + logs + static context)
  2. LLM → {collector_name, reason, confident_enough}
  3. If confident_enough OR budget exhausted → stop
  4. Run the named collector
  5. Append result to evidence snapshot
  6. Go to 2

Collectors available to the planner:
  process_tree         — top processes with parent chain
  scheduler_pressure   — Linux PSI (CPU/IO pressure stall)
  service_ownership    — which systemd unit owns a PID
  memory_breakdown     — /proc/meminfo or WMI breakdown
  oom_history          — kernel OOM kill events
  high_mem_procs       — top processes by RSS
  disk_largest_dirs    — du -sh of common paths
  disk_inode_usage     — df -i per filesystem
  disk_io_wait         — iostat -x
  net_open_ports       — listening ports
  net_connection_summary — connection state counts
  net_dns_errors       — recent DNS/TCP errors in logs
  pg_connections       — pg_stat_activity by state
  pg_long_queries      — queries running > 5 seconds
  service_state        — failed/stopped services
  service_recent_restarts — systemd restart events

Budget: max 4 iterations (configurable via MAX_PLANNER_STEPS)
Each step has its own 10s timeout.
Never raises — returns partial evidence on failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.api.context_collector import (
    _run_with_timeout,
    _cpu_process_tree,
    _cpu_scheduler_pressure,
    _cpu_service_ownership,
    _memory_pressure_breakdown,
    _oom_history,
    _high_mem_processes,
    _disk_largest_dirs,
    _disk_inode_usage,
    _disk_io_wait,
    _net_open_ports,
    _net_connection_summary,
    _net_dns_errors,
    _db_pg_connection_count,
    _db_pg_long_queries,
    _service_state_summary,
    _service_recent_restarts,
)
from app.api.log_collector import format_log_context

_log = logging.getLogger(__name__)

MAX_PLANNER_STEPS = 4
_STEP_TIMEOUT     = 10.0

# ── Collector registry ────────────────────────────────────────────────────────

_COLLECTOR_REGISTRY: dict[str, Any] = {
    "process_tree":            _cpu_process_tree,
    "scheduler_pressure":      _cpu_scheduler_pressure,
    "memory_breakdown":        _memory_pressure_breakdown,
    "oom_history":             _oom_history,
    "high_mem_procs":          _high_mem_processes,
    "disk_largest_dirs":       _disk_largest_dirs,
    "disk_inode_usage":        _disk_inode_usage,
    "disk_io_wait":            _disk_io_wait,
    "net_open_ports":          _net_open_ports,
    "net_connection_summary":  _net_connection_summary,
    "net_dns_errors":          _net_dns_errors,
    "pg_connections":          _db_pg_connection_count,
    "pg_long_queries":         _db_pg_long_queries,
    "service_state":           _service_state_summary,
    "service_recent_restarts": _service_recent_restarts,
}

_COLLECTOR_DESCRIPTIONS = """
Available collectors (choose exactly one name):
  process_tree            - Top processes with PID/parent/CPU%/MEM%
  scheduler_pressure      - Linux PSI: CPU/IO pressure stall info
  memory_breakdown        - Detailed memory breakdown (/proc/meminfo)
  oom_history             - OOM kill events from kernel ring buffer
  high_mem_procs          - Top processes by RSS memory
  disk_largest_dirs       - Largest directories (du -sh)
  disk_inode_usage        - Inode usage per filesystem
  disk_io_wait            - IO wait %, read/write throughput (iostat)
  net_open_ports          - Currently listening ports + owner process
  net_connection_summary  - Connection count by state (ESTABLISHED/WAIT/etc)
  net_dns_errors          - Recent DNS/TCP errors from system logs
  pg_connections          - PostgreSQL connections by state
  pg_long_queries         - Queries running > 5 seconds
  service_state           - Failed or stopped services
  service_recent_restarts - Services that restarted in last 30 minutes
"""

# ── Planner prompt ────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = (
    "You are a senior SRE performing an active incident investigation. "
    "You decide what evidence to collect next based on what you've seen so far. "
    "Respond ONLY with valid JSON — no prose, no markdown."
)

_PLANNER_TEMPLATE = """\
You are investigating a {incident_type} incident.

ALERT: {category} / {severity}
DETAIL: {detail}

CURRENT METRICS:
  CPU: {cpu:.1f}%  Memory: {memory:.1f}%  Disk: {disk:.1f}%

EVIDENCE GATHERED SO FAR:
{evidence_so_far}

ALREADY RUN COLLECTORS: {already_run}

{collector_descriptions}

Based on the evidence so far, decide:
1. Are you confident enough to determine the root cause? (yes/no)
2. If not, which single collector would give you the most useful next piece of evidence?

Return exactly this JSON:
{{
  "confident_enough": <true|false>,
  "collector": "<collector_name or null if confident>",
  "reason": "<one sentence: why this collector OR why you're confident>"
}}
"""


def _format_evidence_snapshot(
    metrics: dict,
    logs: list[dict],
    log_context: str,
    gathered: dict[str, Any],
) -> str:
    lines = []

    lines.append("METRICS:")
    lines.append(f"  CPU {metrics.get('cpu',0):.1f}%  MEM {metrics.get('memory',0):.1f}%  DISK {metrics.get('disk',0):.1f}%")
    load = metrics.get("load_avg_1m")
    if load:
        lines.append(f"  Load 1m: {load}")

    if log_context:
        lines.append("\nLOGS:")
        for line in log_context.strip().splitlines()[:15]:
            lines.append(f"  {line}")

    if gathered:
        lines.append("\nCOLLECTED EVIDENCE:")
        for section, data in gathered.items():
            lines.append(f"  [{section.upper()}]")
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list):
                        for item in v[:6]:
                            lines.append(f"    {item}")
                    else:
                        lines.append(f"    {k}: {str(v)[:150]}")
            elif isinstance(data, list):
                for item in data[:6]:
                    lines.append(f"    {item}")

    return "\n".join(lines)


def _strip_json_obj(raw: str) -> dict:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = raw.find("{")
    stop  = raw.rfind("}") + 1
    if start == -1 or stop == 0:
        return {}
    try:
        return json.loads(raw[start:stop])
    except json.JSONDecodeError:
        return {}


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_evidence_planner(
    incident_type: str,
    metrics: dict[str, Any],
    alert_category: str,
    alert_severity: str,
    alert_detail: str,
    logs: list[dict],
    log_context: str,
    top_cpu_processes: list[dict],
    call_llm_fn: Any,
    max_steps: int = MAX_PLANNER_STEPS,
) -> dict[str, Any]:
    """
    Iteratively gather evidence under LLM guidance.

    Returns:
      {
        "gathered": {collector_name: result_dict, ...},
        "steps":    [{step, collector, reason, confident_enough}, ...],
        "stopped_because": "confident" | "budget" | "llm_error" | "no_collectors_left",
        "context_text": formatted string for LLM prompt injection,
      }
    """
    gathered: dict[str, Any]   = {}
    steps:    list[dict]       = []
    already_run: set[str]      = set()

    stopped_because = "budget"

    for step in range(1, max_steps + 1):
        evidence_snapshot = _format_evidence_snapshot(
            metrics, logs, log_context, gathered
        )

        user_msg = _PLANNER_TEMPLATE.format(
            incident_type=incident_type,
            category=alert_category,
            severity=alert_severity,
            detail=alert_detail,
            cpu=metrics.get("cpu", 0),
            memory=metrics.get("memory", 0),
            disk=metrics.get("disk", 0),
            evidence_so_far=evidence_snapshot,
            already_run=", ".join(sorted(already_run)) or "none",
            collector_descriptions=_COLLECTOR_DESCRIPTIONS,
        )

        try:
            raw = await asyncio.wait_for(
                call_llm_fn(_PLANNER_SYSTEM, user_msg), timeout=20.0
            )
            decision = _strip_json_obj(raw)
        except Exception as exc:
            _log.warning("[evidence_planner] LLM step %d failed: %s", step, exc)
            stopped_because = "llm_error"
            break

        confident  = bool(decision.get("confident_enough", False))
        collector  = str(decision.get("collector") or "").strip()
        reason     = str(decision.get("reason") or "")

        steps.append({
            "step":             step,
            "collector":        collector,
            "reason":           reason[:200],
            "confident_enough": confident,
        })

        _log.info(
            "[evidence_planner] step=%d collector=%s confident=%s reason=%s",
            step, collector, confident, reason[:80]
        )

        if confident:
            stopped_because = "confident"
            break

        if not collector or collector == "null" or collector not in _COLLECTOR_REGISTRY:
            _log.warning("[evidence_planner] unknown collector '%s'", collector)
            stopped_because = "no_collectors_left"
            break

        if collector in already_run:
            _log.info("[evidence_planner] collector '%s' already run, stopping", collector)
            stopped_because = "no_collectors_left"
            break

        # Run the chosen collector
        fn = _COLLECTOR_REGISTRY[collector]

        # Some collectors need arguments — handle those specially
        if collector == "service_ownership":
            coro = fn(top_cpu_processes)
        else:
            coro = fn()

        result = await _run_with_timeout(coro, collector, timeout=_STEP_TIMEOUT)
        gathered[collector] = result
        already_run.add(collector)

    # Format final context text for injection into hypotheses/RCA prompts
    if gathered:
        from app.api.context_collector import format_context_evidence
        context_text = format_context_evidence(gathered)
    else:
        context_text = ""

    return {
        "gathered":        gathered,
        "steps":           steps,
        "stopped_because": stopped_because,
        "context_text":    context_text,
        "steps_taken":     len(steps),
    }
