"""
log_collector.py — Log Intelligence V1 for the investigation engine.

Design (narrow scope, no RAG):
  1. fetch_recent_logs()   — pull last N log lines for an agent from DB
  2. extract_errors()      — filter to ERROR/WARN lines + known patterns
  3. summarize_logs()      — LLM summarises top errors into 3–5 bullet points
  4. build_log_context()   — format log summary + top error lines for LLM prompt injection

The investigation engine calls build_log_evidence() which chains all four steps
and returns an Evidence-compatible dict ready to be merged into Stage 1.

Never raises — all failures return empty/None so investigations still complete.

Log ingestion (how lines get into DB):
  - Agents POST to /agents/{id}/logs  (logs_api.py)
  - Windows Event Log, syslog, journald, app logs
  - Max 500 lines stored per agent; TTL 7 days via cleanup job
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import LogEntry

_log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_FETCH_LIMIT        = 500     # max lines pulled from DB
_ERROR_LINE_LIMIT   = 40      # max error/warn lines sent to LLM
_SUMMARY_LINE_LIMIT = 20      # top lines included verbatim in prompt
_LOOKBACK_MINUTES   = 30      # window around alert time to query logs
_LLM_TIMEOUT        = 20.0    # seconds

# Patterns that always indicate diagnostic value regardless of log level
_HIGH_VALUE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"out\s+of\s+memory",
        r"oom\s+killer",
        r"killed\s+process",
        r"segfault",
        r"connection\s+(refused|reset|timeout|pool\s+exhaust)",
        r"too\s+many\s+(open\s+files|connections|clients)",
        r"disk\s+(full|quota)",
        r"no\s+space\s+left",
        r"swap\s+(full|exhausted)",
        r"cpu\s+(throttl|limit)",
        r"health\s+check\s+fail",
        r"exception|traceback|panic|fatal|critical",
        r"timeout.*\d+\s*(ms|s)",
        r"retry.*\d+\s*of\s*\d+",
        r"circuit\s+breaker",
    ]
]


# ── Log fetching ──────────────────────────────────────────────────────────────

async def fetch_recent_logs(
    db: AsyncSession,
    *,
    agent_id: str,
    org_id: str,
    alert_id: str | None = None,
    around: datetime | None = None,
    limit: int = _FETCH_LIMIT,
) -> list[LogEntry]:
    """
    Fetch recent log lines for an agent.

    If `around` is provided, fetches lines within ±LOOKBACK_MINUTES of that time.
    Otherwise fetches the most recent `limit` lines.
    """
    q = (
        select(LogEntry)
        .where(LogEntry.agent_id == agent_id)
        .where(LogEntry.org_id  == org_id)
    )

    if alert_id:
        # Prefer logs tagged to this specific alert
        q_tagged = q.where(LogEntry.alert_id == alert_id).order_by(desc(LogEntry.collected_at)).limit(limit)
        result = await db.execute(q_tagged)
        rows = result.scalars().all()
        if rows:
            return list(rows)

    if around:
        window_start = around - timedelta(minutes=_LOOKBACK_MINUTES)
        window_end   = around + timedelta(minutes=5)
        q = q.where(LogEntry.collected_at >= window_start).where(LogEntry.collected_at <= window_end)
    
    q = q.order_by(desc(LogEntry.collected_at)).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


# ── Error extraction ──────────────────────────────────────────────────────────

def extract_errors(lines: list[LogEntry]) -> tuple[list[LogEntry], list[LogEntry]]:
    """
    Split log lines into:
      error_lines   — ERROR/WARN level or matching high-value patterns
      high_value    — subset matching specific diagnostic patterns

    Returns (error_lines, high_value_lines)
    """
    error_lines:      list[LogEntry] = []
    high_value_lines: list[LogEntry] = []

    for entry in lines:
        is_error = entry.level.upper() in ("ERROR", "WARN", "WARNING", "CRITICAL", "FATAL")
        text = entry.message or entry.raw_line or ""
        is_high_value = any(p.search(text) for p in _HIGH_VALUE_PATTERNS)

        if is_high_value:
            high_value_lines.append(entry)
        elif is_error:
            error_lines.append(entry)

    return error_lines, high_value_lines


# ── LLM log summary ───────────────────────────────────────────────────────────

_SUMMARY_SYSTEM = """\
You are an expert SRE analysing log output from a production server.
Respond with a bullet-point list only — 3 to 5 bullets, each under 120 characters.
No preamble, no headers, no JSON.
"""

_SUMMARY_TEMPLATE = """\
A {incident_type} incident was detected on agent {agent_id} (CPU={cpu:.0f}%, MEM={mem:.0f}%).

These are the most relevant log lines (newest first):

{log_block}

Summarise the key issues visible in these logs in 3–5 bullet points.
Focus on: errors, resource exhaustion, failed services, timeouts, crashes.
"""


async def summarize_logs(
    lines: list[LogEntry],
    *,
    agent_id: str,
    incident_type: str,
    cpu: float,
    mem: float,
    call_llm_fn: Any,
) -> str | None:
    """
    Ask LLM to produce a concise 3–5 bullet summary of log errors.
    Returns None on failure.
    """
    if not lines:
        return None

    # Build the log block: high-value lines first, then errors, newest first
    chosen = lines[:_SUMMARY_LINE_LIMIT]
    log_block_lines = []
    for e in chosen:
        ts = e.log_ts.strftime("%H:%M:%S") if e.log_ts else "??:??:??"
        msg = (e.message or e.raw_line or "")[:200]
        log_block_lines.append(f"[{ts}] [{e.level}] [{e.source}] {msg}")

    log_block = "\n".join(log_block_lines)

    try:
        raw = await asyncio.wait_for(
            call_llm_fn(_SUMMARY_SYSTEM, _SUMMARY_TEMPLATE.format(
                incident_type=incident_type,
                agent_id=agent_id,
                cpu=cpu,
                mem=mem,
                log_block=log_block,
            )),
            timeout=_LLM_TIMEOUT,
        )
        return raw.strip() if raw else None
    except Exception as exc:
        _log.warning("[LOGS] LLM summarization failed: %s", exc)
        return None


# ── Build log context (main entry point) ─────────────────────────────────────

async def build_log_evidence(
    db: AsyncSession,
    *,
    agent_id: str,
    org_id: str,
    alert_id: str | None,
    incident_type: str,
    cpu: float,
    memory: float,
    alert_time: datetime | None = None,
    call_llm_fn: Any | None = None,
) -> dict[str, Any]:
    """
    Collect and summarise logs for one investigation evidence block.

    Returns a dict with:
      log_line_count       : int   — total lines fetched
      error_line_count     : int   — ERROR/WARN lines
      high_value_count     : int   — lines matching critical patterns
      top_errors           : list[str]  — top 10 error messages
      high_value_lines     : list[str]  — top 10 diagnostic lines
      log_summary          : str | None — LLM bullet-point summary
      log_collection_note  : str   — human-readable status
    """
    result: dict[str, Any] = {
        "log_line_count":      0,
        "error_line_count":    0,
        "high_value_count":    0,
        "top_errors":          [],
        "high_value_lines":    [],
        "log_summary":         None,
        "log_collection_note": "no logs collected",
    }

    try:
        lines = await fetch_recent_logs(
            db,
            agent_id=agent_id,
            org_id=org_id,
            alert_id=alert_id,
            around=alert_time or datetime.now(timezone.utc),
        )

        if not lines:
            result["log_collection_note"] = "no log lines available for this agent"
            return result

        result["log_line_count"] = len(lines)

        error_lines, high_value_lines = extract_errors(lines)
        result["error_line_count"]  = len(error_lines)
        result["high_value_count"]  = len(high_value_lines)

        # Top error messages (deduplicated)
        seen: set[str] = set()
        top_errors: list[str] = []
        for e in (high_value_lines + error_lines)[:_ERROR_LINE_LIMIT]:
            msg = (e.message or e.raw_line or "").strip()[:200]
            if msg and msg not in seen:
                seen.add(msg)
                top_errors.append(f"[{e.level}] {msg}")
                if len(top_errors) >= 10:
                    break

        result["top_errors"]       = top_errors
        result["high_value_lines"] = [
            f"[{e.log_ts.strftime('%H:%M:%S') if e.log_ts else '?'}] {(e.message or '')[:200]}"
            for e in high_value_lines[:10]
        ]

        # LLM summary (requires call_llm_fn + at least some relevant lines)
        diagnostic_lines = high_value_lines[:_SUMMARY_LINE_LIMIT] or error_lines[:_SUMMARY_LINE_LIMIT]
        if diagnostic_lines and call_llm_fn is not None:
            summary = await summarize_logs(
                diagnostic_lines,
                agent_id=agent_id,
                incident_type=incident_type,
                cpu=cpu,
                mem=memory,
                call_llm_fn=call_llm_fn,
            )
            result["log_summary"] = summary

        total_useful = len(top_errors)
        result["log_collection_note"] = (
            f"{len(lines)} lines fetched; "
            f"{len(error_lines)} errors, {len(high_value_lines)} high-value patterns; "
            f"{'LLM summary generated' if result['log_summary'] else 'no LLM summary'}"
        )

        _log.info(
            "[LOGS] agent=%s lines=%d errors=%d high_value=%d summary=%s",
            agent_id[:8], len(lines), len(error_lines), len(high_value_lines),
            result["log_summary"] is not None,
        )

    except Exception as exc:
        _log.warning("[LOGS] Log collection failed for agent=%s: %s", agent_id, exc)
        result["log_collection_note"] = f"log collection error: {exc}"

    return result


# ── Format for LLM prompt injection ──────────────────────────────────────────

def format_log_context(log_evidence: dict[str, Any]) -> str:
    """
    Format the log evidence dict into a structured block for LLM prompts.
    Injected into investigation Stage 1 evidence and Stage 3/4 prompts.
    """
    if not log_evidence or log_evidence.get("log_line_count", 0) == 0:
        return "LOG INTELLIGENCE:\n  (no logs available)\n"

    lines = [
        f"LOG INTELLIGENCE ({log_evidence['log_line_count']} lines, "
        f"{log_evidence['error_line_count']} errors, "
        f"{log_evidence['high_value_count']} critical patterns):"
    ]

    if log_evidence.get("log_summary"):
        lines.append("\nSummary:")
        for bullet in log_evidence["log_summary"].splitlines():
            b = bullet.strip()
            if b:
                lines.append(f"  {b}")

    if log_evidence.get("high_value_lines"):
        lines.append("\nCritical log lines:")
        for l in log_evidence["high_value_lines"][:5]:
            lines.append(f"  {l}")

    if log_evidence.get("top_errors"):
        lines.append("\nTop errors:")
        for e in log_evidence["top_errors"][:5]:
            lines.append(f"  {e}")

    lines.append("")
    return "\n".join(lines)
