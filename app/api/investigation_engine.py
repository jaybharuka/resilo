"""
investigation_engine.py — Multi-stage AI investigation pipeline.

Replaces the direct Metrics → LLM → Action flow with:

  Alert detected
      ↓
  EVIDENCE_COLLECTION   — gather structured metric evidence
      ↓
  HISTORICAL_ANALYSIS   — retrieve similar past incidents
      ↓
  HYPOTHESIS_GENERATION — LLM generates 3-5 ranked hypotheses
      ↓
  ROOT_CAUSE_ANALYSIS   — LLM determines root cause with evidence chain
      ↓
  ACTION_PLANNING       — confidence-based routing

Confidence routing:
  ≥ 95%   → AUTO_EXECUTE
  70–94%  → MANUAL_APPROVAL
  < 70%   → INVESTIGATION_ONLY  (record only, no action)

Designed to be called from _lc_analyze() as a drop-in replacement.
Never raises — all stage errors are logged and the engine degrades gracefully.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    AgentActionLog, AlertRecord, Investigation, MetricSnapshot, SessionLocal,
)
from app.api.incident_memory import build_memory_context
from app.api.memory_store import MemoryStore
from app.api.log_collector import build_log_evidence, format_log_context
from app.api.context_collector import collect_context, format_context_evidence
from app.api.evidence_planner import run_evidence_planner

_log = logging.getLogger(__name__)


# ── Stage definitions ─────────────────────────────────────────────────────────

class InvestigationStage(str, Enum):
    EVIDENCE_COLLECTION   = "EVIDENCE_COLLECTION"
    HISTORICAL_ANALYSIS   = "HISTORICAL_ANALYSIS"
    HYPOTHESIS_GENERATION = "HYPOTHESIS_GENERATION"
    ROOT_CAUSE_ANALYSIS   = "ROOT_CAUSE_ANALYSIS"
    ACTION_PLANNING       = "ACTION_PLANNING"


class ActionRouting(str, Enum):
    AUTO_EXECUTE        = "auto_execute"
    MANUAL_APPROVAL     = "manual_approval"
    INVESTIGATION_ONLY  = "investigation_only"


# ── Confidence thresholds ─────────────────────────────────────────────────────

CONFIDENCE_AUTO_EXECUTE   = 0.95   # ≥ this → auto execute
CONFIDENCE_MANUAL_APPROVAL = 0.70  # ≥ this → manual approval; below → investigate only


# ── Pydantic models ───────────────────────────────────────────────────────────

class Evidence(BaseModel):
    incident_type: str                        # cpu|memory|disk|network
    cpu: float
    memory: float
    disk: float
    load_avg_1m: float | None = None
    swap_percent: float | None = None
    net_established: int | None = None
    top_cpu_processes: list[dict] = Field(default_factory=list)
    top_mem_processes: list[dict] = Field(default_factory=list)
    recent_action_count: int = 0
    last_action: str | None = None
    last_action_success: bool | None = None
    collection_note: str = ""
    # ── Log intelligence (Phase 3) ─────────────────────────────────────────
    log_line_count:     int = 0
    error_line_count:   int = 0
    high_value_count:   int = 0
    top_errors:         list[str] = Field(default_factory=list)
    high_value_lines:   list[str] = Field(default_factory=list)
    log_summary:        str | None = None
    log_context:        str = ""   # formatted block for LLM injection
    # ── Dynamic context evidence (Phase 4) ────────────────────────────────
    context_evidence:   dict = Field(default_factory=dict)
    context_text:       str = ""   # formatted block for LLM injection


class Hypothesis(BaseModel):
    cause: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)


class RootCauseAnalysis(BaseModel):
    root_cause: str
    confidence: float
    supporting_evidence: list[str] = Field(default_factory=list)
    historical_matches: list[str] = Field(default_factory=list)
    reasoning_steps: list[str] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    investigation_id: str
    agent_id: str
    alert_id: str | None
    evidence: Evidence
    similar_incidents: list[dict] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    root_cause: RootCauseAnalysis
    recommended_action: str
    confidence: float
    action_routing: ActionRouting
    timeline: list[dict] = Field(default_factory=list)
    memory_id: str | None = None
    # ── Cost telemetry (Phase 5) ─────────────────────────────────────────────
    llm_cost: dict = Field(default_factory=dict)  # {llm_calls, est_tokens, total_llm_ms, avg_llm_ms}
    # ── Evidence contribution (Phase 5) ──────────────────────────────────────
    evidence_contribution: dict = Field(default_factory=dict)  # {logs_helped, memory_helped, context_helped, planner_helped}


# ── Evidence contribution scorer ────────────────────────────────────────────────

def _score_evidence_contribution(
    evidence: "Evidence",
    rca: "RootCauseAnalysis",
    similar: list[dict],
    memories_used: int,
) -> dict[str, Any]:
    """
    Heuristically determine which evidence sources materially influenced
    the RCA conclusion.  No extra LLM call — derived from existing artefacts.

    Logic:
      logs_helped    — error lines > 0 AND any top_error keyword appears in root_cause
      memory_helped  — at least one retrieved memory was referenced in rca.historical_matches
      context_helped — context_evidence has sections AND any section key appears in root_cause
      planner_helped — planner gathered data (planner key in context_evidence)
    """
    rc_lower = rca.root_cause.lower()
    evidence_text = " ".join(rca.supporting_evidence).lower()
    combined = rc_lower + " " + evidence_text

    # Logs: did any logged error string appear verbatim or near-verbatim in the RCA?
    logs_helped = False
    if evidence.error_line_count > 0:
        for line in evidence.top_errors[:10]:
            # take the first 6 words of the log line as a fingerprint
            words = line.lower().split()
            if len(words) >= 3 and any(
                " ".join(words[i : i + 3]) in combined for i in range(min(len(words) - 2, 5))
            ):
                logs_helped = True
                break
        # fallback: if error_line_count high and confidence ≥ 0.7, logs likely helped
        if not logs_helped and evidence.error_line_count >= 3 and rca.confidence >= 0.70:
            logs_helped = True

    # Memory: referenced in historical_matches?
    memory_helped = memories_used > 0

    # Context: any context section key name appears in combined text?
    ctx_keys = [
        k for k in evidence.context_evidence.keys() if k != "planner"
    ]
    context_helped = bool(ctx_keys) and any(
        k.replace("_", " ") in combined or k.replace("_", "") in combined
        for k in ctx_keys
    )
    # fallback: if context was collected and confidence is high, it likely helped
    if not context_helped and ctx_keys and rca.confidence >= 0.75:
        context_helped = True

    # Planner: did it gather additional evidence?
    planner_helped = bool(evidence.context_evidence.get("planner"))

    return {
        "logs_helped":    logs_helped,
        "memory_helped":  memory_helped,
        "context_helped": context_helped,
        "planner_helped": planner_helped,
        "error_lines":    evidence.error_line_count,
        "memory_matches": len(similar),
        "context_sections": len(ctx_keys),
    }


# ── LLM cost tracker ────────────────────────────────────────────────────────

class LLMCallTracker:
    """
    Wraps a call_llm_fn to count calls, estimate tokens, and track latency.
    Use as a drop-in replacement for call_llm_fn inside a single investigation.
    """
    def __init__(self, fn: Any) -> None:
        self._fn            = fn
        self.calls:    int  = 0
        self.tokens:   int  = 0   # rough estimate: chars / 4
        self.total_ms: float = 0.0

    async def __call__(self, system: str, user: str) -> str:
        import time as _time
        t0  = _time.monotonic()
        raw = await self._fn(system, user)
        elapsed_ms = (_time.monotonic() - t0) * 1000
        self.calls      += 1
        self.total_ms   += elapsed_ms
        self.tokens     += (len(system) + len(user) + len(raw or "")) // 4
        return raw

    def summary(self) -> dict[str, Any]:
        return {
            "llm_calls":   self.calls,
            "est_tokens":  self.tokens,
            "total_llm_ms": round(self.total_ms, 1),
            "avg_llm_ms":  round(self.total_ms / max(self.calls, 1), 1),
        }


# ── Helper utilities ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timeline_event(stage: InvestigationStage | str, event: str) -> dict:
    stage_str = stage.value if isinstance(stage, InvestigationStage) else str(stage)
    return {"timestamp": _now_iso(), "stage": stage_str, "event": event}


def _strip_json(raw: str) -> dict:
    """Extract the first JSON object from an LLM response that may include prose."""
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {}


def _strip_json_array(raw: str) -> list:
    """Extract the first JSON array from an LLM response."""
    start = raw.find("[")
    end   = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return []


# ── Stage 1: Evidence Collection ─────────────────────────────────────────────

async def _collect_evidence(
    db: AsyncSession,
    agent_id: str,
    org_id: str,
    cpu: float,
    memory: float,
    disk: float,
    alert: AlertRecord,
    extra_metrics: dict[str, Any] | None = None,
    call_llm_fn: Any = None,
) -> tuple[Evidence, list[dict]]:
    """Gather all available evidence about the current incident."""
    timeline: list[dict] = []
    timeline.append(_timeline_event(InvestigationStage.EVIDENCE_COLLECTION, "Evidence collection started"))

    extra = extra_metrics or {}
    top_processes: dict = extra.get("top_processes") or {}
    top_cpu: list[dict] = (top_processes.get("by_cpu") or [])[:5]
    top_mem: list[dict] = (top_processes.get("by_mem") or [])[:5]

    # Determine primary incident type from alert category and current metrics
    category = (alert.category or "").lower()
    if "cpu" in category or cpu >= 85:
        incident_type = "cpu"
    elif "memory" in category or memory >= 85:
        incident_type = "memory"
    elif "disk" in category or disk >= 85:
        incident_type = "disk"
    elif "network" in category:
        incident_type = "network"
    else:
        incident_type = "cpu"

    # Look up the last 3 action log entries for this agent
    action_result = await db.execute(
        select(AgentActionLog)
        .where(AgentActionLog.agent_id == agent_id)
        .order_by(AgentActionLog.created_at.desc())
        .limit(3)
    )
    recent_actions = action_result.scalars().all()
    last_action = recent_actions[0].action if recent_actions else None
    last_action_success = recent_actions[0].success if recent_actions else None

    note_parts: list[str] = [f"Incident type: {incident_type}"]
    if top_cpu:
        note_parts.append(f"Top CPU: {top_cpu[0].get('name', '?')} at {top_cpu[0].get('cpu_percent', 0):.1f}%")
    if top_mem:
        note_parts.append(f"Top Mem: {top_mem[0].get('name', '?')} at {top_mem[0].get('memory_percent', 0):.1f}%")

    # ── Log intelligence ────────────────────────────────────────────────────
    log_ev = await build_log_evidence(
        db,
        agent_id=agent_id,
        org_id=org_id,
        alert_id=alert.id,
        incident_type=incident_type,
        cpu=cpu,
        memory=memory,
        alert_time=alert.created_at if hasattr(alert, "created_at") else None,
        call_llm_fn=call_llm_fn,
    )
    log_ctx = format_log_context(log_ev)

    # ── Dynamic context evidence ───────────────────────────────────────────
    ctx_evidence = await collect_context(
        incident_type=incident_type,
        top_cpu_processes=top_cpu,
        top_mem_processes=top_mem,
    )
    ctx_text = format_context_evidence(ctx_evidence)

    if log_ev["log_line_count"] > 0:
        note_parts.append(
            f"Logs: {log_ev['log_line_count']} lines, "
            f"{log_ev['error_line_count']} errors, "
            f"{log_ev['high_value_count']} critical patterns"
        )

    evidence = Evidence(
        incident_type=incident_type,
        cpu=cpu,
        memory=memory,
        disk=disk,
        load_avg_1m=extra.get("load_avg_1m"),
        swap_percent=extra.get("swap_percent"),
        net_established=extra.get("net_established"),
        top_cpu_processes=top_cpu,
        top_mem_processes=top_mem,
        recent_action_count=len(recent_actions),
        last_action=last_action,
        last_action_success=last_action_success,
        collection_note="; ".join(note_parts),
        log_line_count=log_ev["log_line_count"],
        error_line_count=log_ev["error_line_count"],
        high_value_count=log_ev["high_value_count"],
        top_errors=log_ev["top_errors"],
        high_value_lines=log_ev["high_value_lines"],
        log_summary=log_ev["log_summary"],
        log_context=log_ctx,
        context_evidence=ctx_evidence,
        context_text=ctx_text,
    )

    timeline.append(_timeline_event(
        InvestigationStage.EVIDENCE_COLLECTION,
        f"Evidence collected: type={incident_type} cpu={cpu:.1f}% mem={memory:.1f}% disk={disk:.1f}% "
        f"logs={log_ev['log_line_count']}lines/{log_ev['error_line_count']}errors "
        f"ctx_sections={len(ctx_evidence)}",
    ))
    return evidence, timeline


# ── Stage 2: Historical Analysis ─────────────────────────────────────────────

async def _historical_analysis(
    db: AsyncSession,
    org_id: str,
    evidence: Evidence,
    alert: AlertRecord,
    timeline: list[dict],
) -> tuple[list[dict], str, dict]:
    """Retrieve similar incidents using semantic search and build the memory context block."""
    timeline.append(_timeline_event(
        InvestigationStage.HISTORICAL_ANALYSIS, "Searching historical incident memory (semantic)"
    ))

    metrics_dict = {
        "cpu": evidence.cpu,
        "memory": evidence.memory,
        "disk": evidence.disk,
    }
    similar, telemetry = await MemoryStore.search(
        db,
        org_id=org_id,
        category=evidence.incident_type,
        severity=alert.severity,
        metrics=metrics_dict,
        root_cause_hint=alert.detail or "",
        limit=5,
    )

    n = len(similar)
    method = telemetry.get("method", "keyword")
    timeline.append(_timeline_event(
        InvestigationStage.HISTORICAL_ANALYSIS,
        f"Found {n} similar incident(s) via {method} search "
        f"(retrieval={telemetry.get('retrieval_time_ms', 0):.0f}ms)"
        if n else
        f"No similar incidents in memory ({method} search, {telemetry.get('retrieval_time_ms', 0):.0f}ms)",
    ))

    memory_context = build_memory_context(similar)
    return similar, memory_context, telemetry


# ── Stage 3: Hypothesis Generation ───────────────────────────────────────────

_HYPOTHESIS_SYSTEM = """\
You are a senior SRE performing root cause analysis.
Respond with valid JSON only — no markdown, no prose outside the array.
"""

_HYPOTHESIS_TEMPLATE = """\
A {incident_type} incident was detected on agent {agent_id}.

CURRENT METRICS:
  CPU:    {cpu:.1f}%
  Memory: {memory:.1f}%
  Disk:   {disk:.1f}%
  Load 1m: {load_avg_1m}
  Swap:    {swap}%
  Active connections: {net_established}

ALERT:
  Category: {category}
  Severity: {severity}
  Detail:   {detail}

TOP PROCESSES (CPU):
{top_cpu_lines}

TOP PROCESSES (MEMORY):
{top_mem_lines}

{log_context}
{context_text}
{memory_context}

Generate 3 to 5 hypotheses explaining this incident.
Return a JSON array of objects — each with exactly these keys:
  "cause"      — one-sentence hypothesis
  "confidence" — float 0.0 to 1.0
  "evidence"   — list of strings citing supporting evidence from the data above

Example: [{{"cause": "...", "confidence": 0.85, "evidence": ["cpu=92%", "top process: python at 88%"]}}]
"""


async def _generate_hypotheses(
    evidence: Evidence,
    alert: AlertRecord,
    agent_id: str,
    memory_context: str,
    call_llm_fn: Any,
    timeline: list[dict],
) -> list[Hypothesis]:
    """Call LLM to produce 3-5 ranked hypotheses."""
    timeline.append(_timeline_event(
        InvestigationStage.HYPOTHESIS_GENERATION, "Generating hypotheses via LLM"
    ))

    top_cpu_lines = "\n".join(
        f"  {p.get('name', '?')} — cpu={p.get('cpu_percent', 0):.1f}%"
        for p in evidence.top_cpu_processes
    ) or "  (none)"
    top_mem_lines = "\n".join(
        f"  {p.get('name', '?')} — mem={p.get('memory_percent', 0):.1f}%"
        for p in evidence.top_mem_processes
    ) or "  (none)"

    user_msg = _HYPOTHESIS_TEMPLATE.format(
        incident_type=evidence.incident_type,
        agent_id=agent_id,
        cpu=evidence.cpu,
        memory=evidence.memory,
        disk=evidence.disk,
        load_avg_1m=evidence.load_avg_1m if evidence.load_avg_1m is not None else "N/A",
        swap=evidence.swap_percent if evidence.swap_percent is not None else "N/A",
        net_established=evidence.net_established if evidence.net_established is not None else "N/A",
        category=alert.category,
        severity=alert.severity,
        detail=alert.detail or "",
        top_cpu_lines=top_cpu_lines,
        top_mem_lines=top_mem_lines,
        log_context=evidence.log_context or "",
        context_text=evidence.context_text or "",
        memory_context=memory_context,
    )

    hypotheses: list[Hypothesis] = []
    try:
        raw = await asyncio.wait_for(
            call_llm_fn(_HYPOTHESIS_SYSTEM, user_msg), timeout=30.0
        )
        raw_list = _strip_json_array(raw)
        for item in raw_list[:5]:
            if not isinstance(item, dict):
                continue
            hypotheses.append(Hypothesis(
                cause=str(item.get("cause", "Unknown cause")),
                confidence=float(item.get("confidence", 0.5)),
                evidence=list(item.get("evidence") or []),
            ))
    except Exception as exc:
        _log.warning("[INVESTIGATE] Hypothesis generation failed: %s", exc)

    # Always have at least one hypothesis (rule-based fallback)
    if not hypotheses:
        hypotheses = _fallback_hypotheses(evidence)

    # Sort by confidence descending
    hypotheses.sort(key=lambda h: h.confidence, reverse=True)

    timeline.append(_timeline_event(
        InvestigationStage.HYPOTHESIS_GENERATION,
        f"Generated {len(hypotheses)} hypotheses; top: {hypotheses[0].cause[:80]}",
    ))
    return hypotheses


def _fallback_hypotheses(evidence: Evidence) -> list[Hypothesis]:
    """Deterministic hypotheses when LLM is unavailable."""
    if evidence.incident_type == "cpu":
        return [
            Hypothesis(cause="Runaway process consuming all CPU capacity",
                       confidence=0.65, evidence=[f"cpu={evidence.cpu:.1f}%"]),
            Hypothesis(cause="Scheduled job or batch workload spike",
                       confidence=0.45, evidence=[f"cpu={evidence.cpu:.1f}%"]),
        ]
    if evidence.incident_type == "memory":
        return [
            Hypothesis(cause="Memory leak in long-running process",
                       confidence=0.70, evidence=[f"memory={evidence.memory:.1f}%"]),
            Hypothesis(cause="Cache growth exceeding available RAM",
                       confidence=0.50, evidence=[f"memory={evidence.memory:.1f}%"]),
        ]
    if evidence.incident_type == "disk":
        return [
            Hypothesis(cause="Log files or temp data filling disk",
                       confidence=0.75, evidence=[f"disk={evidence.disk:.1f}%"]),
        ]
    return [
        Hypothesis(cause="Unclassified resource pressure",
                   confidence=0.40, evidence=[]),
    ]


# ── Stage 4: Root Cause Analysis ─────────────────────────────────────────────

_RCA_SYSTEM = """\
You are a senior SRE performing root cause analysis on a live incident.
Respond with valid JSON only — no markdown, no prose outside the object.
"""

_RCA_TEMPLATE = """\
Incident context:
  Agent:    {agent_id}
  Type:     {incident_type}
  CPU:      {cpu:.1f}%   Memory: {memory:.1f}%   Disk: {disk:.1f}%
  Alert:    {category} / {severity}

Top hypotheses (ranked by confidence):
{hypotheses_block}

{log_context}
{context_text}
{memory_context}

Perform root cause analysis and return exactly this JSON object:
{{
  "root_cause":          "<one clear sentence>",
  "confidence":          <0.0-1.0>,
  "supporting_evidence": ["<fact1>", "<fact2>", ...],
  "historical_matches":  ["<reference to any historical match that supports this>"],
  "reasoning_steps":     ["<step1>", "<step2>", "<step3>"],
  "recommended_action":  "<one of: free_memory|disk_cleanup|clear_cache|run_gc|kill_process|restart_service|notify_only>",
  "safe_to_auto_fix":    <true|false>
}}
"""


async def _root_cause_analysis(
    evidence: Evidence,
    alert: AlertRecord,
    agent_id: str,
    hypotheses: list[Hypothesis],
    similar_incidents: list[dict],
    memory_context: str,
    call_llm_fn: Any,
    timeline: list[dict],
) -> tuple[RootCauseAnalysis, str]:
    """Synthesise evidence and hypotheses into a final root cause."""
    timeline.append(_timeline_event(
        InvestigationStage.ROOT_CAUSE_ANALYSIS, "Starting root cause analysis"
    ))

    hypotheses_block = "\n".join(
        f"  [{i+1}] {h.cause} (confidence={h.confidence:.2f})"
        for i, h in enumerate(hypotheses[:5])
    )
    hist_refs = [m.get("title", "") for m in similar_incidents[:3]]

    user_msg = _RCA_TEMPLATE.format(
        agent_id=agent_id,
        incident_type=evidence.incident_type,
        cpu=evidence.cpu,
        memory=evidence.memory,
        disk=evidence.disk,
        category=alert.category,
        severity=alert.severity,
        hypotheses_block=hypotheses_block,
        log_context=evidence.log_context or "",
        context_text=evidence.context_text or "",
        memory_context=memory_context,
    )

    rca: RootCauseAnalysis | None = None
    recommended_action = "notify_only"

    try:
        raw = await asyncio.wait_for(
            call_llm_fn(_RCA_SYSTEM, user_msg), timeout=30.0
        )
        data = _strip_json(raw)
        if data:
            rca = RootCauseAnalysis(
                root_cause=str(data.get("root_cause", hypotheses[0].cause)),
                confidence=float(data.get("confidence", hypotheses[0].confidence)),
                supporting_evidence=list(data.get("supporting_evidence") or []),
                historical_matches=list(data.get("historical_matches") or hist_refs),
                reasoning_steps=list(data.get("reasoning_steps") or []),
            )
            recommended_action = str(data.get("recommended_action", "notify_only"))
    except Exception as exc:
        _log.warning("[INVESTIGATE] RCA LLM call failed: %s", exc)

    if rca is None:
        # Fallback: use top hypothesis
        rca = RootCauseAnalysis(
            root_cause=hypotheses[0].cause,
            confidence=hypotheses[0].confidence,
            supporting_evidence=hypotheses[0].evidence,
            historical_matches=hist_refs,
            reasoning_steps=[
                f"Alert: {alert.category} at {evidence.cpu:.1f}%/{evidence.memory:.1f}%",
                f"Top hypothesis: {hypotheses[0].cause}",
                "LLM analysis unavailable — using rule fallback",
            ],
        )
        # Derive action from rule fallback
        if evidence.incident_type == "memory":
            recommended_action = "free_memory"
        elif evidence.incident_type == "disk":
            recommended_action = "disk_cleanup"
        elif evidence.incident_type == "cpu":
            recommended_action = "free_memory"

    timeline.append(_timeline_event(
        InvestigationStage.ROOT_CAUSE_ANALYSIS,
        f"Root cause identified (confidence={rca.confidence:.0%}): {rca.root_cause[:100]}",
    ))
    return rca, recommended_action


# ── Stage 5: Action Planning / Confidence Routing ────────────────────────────

def _route_action(confidence: float) -> ActionRouting:
    """Map AI confidence to an execution decision."""
    if confidence >= CONFIDENCE_AUTO_EXECUTE:
        return ActionRouting.AUTO_EXECUTE
    if confidence >= CONFIDENCE_MANUAL_APPROVAL:
        return ActionRouting.MANUAL_APPROVAL
    return ActionRouting.INVESTIGATION_ONLY


# ── Persistence helpers ───────────────────────────────────────────────────────

async def _persist_investigation(
    inv_id: str,
    org_id: str,
    agent_id: str,
    alert_id: str | None,
    evidence: Evidence,
    similar: list[dict],
    hypotheses: list[Hypothesis],
    rca: RootCauseAnalysis,
    recommended_action: str,
    routing: ActionRouting,
    timeline: list[dict],
    retrieval_telemetry: dict | None = None,
    llm_cost: dict | None = None,
    evidence_contribution: dict | None = None,
) -> None:
    """Upsert Investigation row into DB."""
    telem = retrieval_telemetry or {}

    # Count how many retrieved memories were actually referenced in final RCA
    hist_refs: list[str] = rca.historical_matches or []
    mem_titles: list[str] = [m.get("title", "") for m in (similar or [])]
    memories_used = sum(
        1 for title in mem_titles
        if title and any(title[:40].lower() in ref.lower() for ref in hist_refs)
    )

    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Investigation).where(Investigation.id == inv_id)
            )
            inv = result.scalar_one_or_none()
            if inv is None:
                inv = Investigation(id=inv_id, org_id=org_id, agent_id=agent_id)
                db.add(inv)

            inv.alert_id                    = alert_id
            inv.status                      = "completed"
            inv.stage                       = "ACTION_PLANNING"
            inv.evidence                    = evidence.model_dump()
            inv.similar_incidents           = similar
            inv.hypotheses                  = [h.model_dump() for h in hypotheses]
            inv.root_cause                  = rca.model_dump()
            inv.recommended_action          = recommended_action
            inv.confidence                  = rca.confidence
            inv.action_routing              = routing.value
            inv.timeline                    = timeline
            inv.semantic_hits               = telem.get("semantic_hits")
            inv.avg_similarity              = telem.get("avg_similarity")
            inv.retrieval_time_ms           = telem.get("retrieval_time_ms")
            inv.memories_used_in_reasoning  = memories_used
            inv.context_evidence            = evidence.context_evidence or {}
            inv.llm_cost                    = llm_cost or {}
            inv.evidence_contribution       = evidence_contribution or {}
            inv.completed_at                = datetime.now(timezone.utc)
            await db.commit()
    except Exception as exc:
        _log.error("[INVESTIGATE] Failed to persist investigation %s: %s", inv_id, exc)


async def _persist_failed_investigation(
    inv_id: str,
    org_id: str,
    agent_id: str,
    alert_id: str | None,
    stage: str,
    timeline: list[dict],
    error: str,
) -> None:
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Investigation).where(Investigation.id == inv_id)
            )
            inv = result.scalar_one_or_none()
            if inv is None:
                inv = Investigation(id=inv_id, org_id=org_id, agent_id=agent_id)
                db.add(inv)
            timeline.append(_timeline_event(stage, f"Investigation failed: {error}"))
            inv.alert_id    = alert_id
            inv.status      = "failed"
            inv.stage       = stage
            inv.timeline    = timeline
            inv.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as exc:
        _log.error("[INVESTIGATE] Failed to persist failed investigation %s: %s", inv_id, exc)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_investigation(
    *,
    db: AsyncSession,
    alert: AlertRecord,
    org_id: str,
    agent_id: str,
    cpu: float,
    memory: float,
    disk: float,
    extra_metrics: dict[str, Any] | None = None,
    call_llm_fn: Any,
) -> InvestigationResult:
    """
    Execute the full 5-stage investigation pipeline for a single alert.

    Parameters
    ----------
    db            : Active async session for DB reads (evidence, memory search).
    alert         : The AlertRecord that triggered this investigation.
    org_id        : Organisation scope.
    agent_id      : The reporting agent.
    cpu/memory/disk: Current metric values.
    extra_metrics : Optional dict from the heartbeat (top_processes, load_avg_1m, …).
    call_llm_fn   : Async callable(system_prompt, user_msg) → str.
                    Pass runtime._call_llm.

    Returns InvestigationResult with all stage outputs.
    Never raises — failures degrade to fallback results.
    """
    now = datetime.now(timezone.utc)
    inv_id = f"INV-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    _log.info("[INVESTIGATE] Starting investigation %s agent=%s alert=%s",
              inv_id, agent_id, alert.id)

    # Wrap LLM calls so cost is tracked for this entire investigation
    tracker = LLMCallTracker(call_llm_fn) if call_llm_fn else None
    call_llm_fn = tracker  # type: ignore[assignment]

    # Create the DB row immediately so the API can see "running" status
    try:
        inv_row = Investigation(
            id=inv_id,
            org_id=org_id,
            agent_id=agent_id,
            alert_id=alert.id,
            status="running",
            stage=InvestigationStage.EVIDENCE_COLLECTION.value,
            timeline=[_timeline_event(InvestigationStage.EVIDENCE_COLLECTION, "Investigation started")],
        )
        db.add(inv_row)
        await db.flush()
    except Exception as exc:
        _log.warning("[INVESTIGATE] Could not pre-create investigation row: %s", exc)

    # ── Stage 1: Evidence Collection ─────────────────────────────────────────
    try:
        evidence, timeline = await _collect_evidence(
            db, agent_id, org_id, cpu, memory, disk, alert, extra_metrics, call_llm_fn
        )
    except Exception as exc:
        _log.error("[INVESTIGATE] Evidence collection failed: %s", exc)
        await _persist_failed_investigation(
            inv_id, org_id, agent_id, alert.id,
            InvestigationStage.EVIDENCE_COLLECTION.value,
            [_timeline_event(InvestigationStage.EVIDENCE_COLLECTION, "Investigation started")],
            str(exc),
        )
        return _minimal_result(inv_id, agent_id, alert.id, cpu, memory, disk)

    # ── Stage 1.5: Adaptive Evidence Planning (Phase 5) ───────────────────
    use_planner = (extra_metrics or {}).get("use_evidence_planner", False)
    if use_planner and call_llm_fn:
        try:
            planner_result = await run_evidence_planner(
                incident_type=evidence.incident_type,
                metrics={
                    "cpu":         cpu,
                    "memory":      memory,
                    "disk":        disk,
                    "load_avg_1m": evidence.load_avg_1m,
                },
                alert_category=alert.category,
                alert_severity=alert.severity,
                alert_detail=alert.detail or "",
                logs=evidence.top_errors,
                log_context=evidence.log_context,
                top_cpu_processes=evidence.top_cpu_processes,
                call_llm_fn=call_llm_fn,
            )
            # Merge planner context into evidence (override static context)
            if planner_result["gathered"]:
                evidence = evidence.model_copy(update={
                    "context_evidence": {
                        **evidence.context_evidence,
                        "planner": planner_result["gathered"],
                    },
                    "context_text": planner_result["context_text"] or evidence.context_text,
                })
            timeline.append(_timeline_event(
                InvestigationStage.EVIDENCE_COLLECTION,
                f"Evidence planner: {planner_result['steps_taken']} steps, "
                f"stopped={planner_result['stopped_because']}",
            ))
            _log.info(
                "[INVESTIGATE] Planner finished: steps=%d stopped=%s",
                planner_result["steps_taken"], planner_result["stopped_because"]
            )
        except Exception as exc:
            _log.warning("[INVESTIGATE] Evidence planner failed (non-fatal): %s", exc)

    # ── Stage 2: Historical Analysis ─────────────────────────────────────────
    retrieval_telemetry: dict = {}
    try:
        similar, memory_context, retrieval_telemetry = await _historical_analysis(
            db, org_id, evidence, alert, timeline
        )
    except Exception as exc:
        _log.warning("[INVESTIGATE] Historical analysis failed: %s", exc)
        similar, memory_context = [], "HISTORICAL MATCHES:\n  (unavailable)\n"
        timeline.append(_timeline_event(
            InvestigationStage.HISTORICAL_ANALYSIS, f"Historical analysis skipped: {exc}"
        ))

    # ── Stage 3: Hypothesis Generation ───────────────────────────────────────
    try:
        hypotheses = await _generate_hypotheses(
            evidence, alert, agent_id, memory_context, call_llm_fn, timeline
        )
    except Exception as exc:
        _log.warning("[INVESTIGATE] Hypothesis generation failed: %s", exc)
        hypotheses = _fallback_hypotheses(evidence)
        timeline.append(_timeline_event(
            InvestigationStage.HYPOTHESIS_GENERATION,
            f"Hypothesis generation fallback: {exc}",
        ))

    # ── Stage 4: Root Cause Analysis ─────────────────────────────────────────
    try:
        rca, recommended_action = await _root_cause_analysis(
            evidence, alert, agent_id, hypotheses, similar, memory_context,
            call_llm_fn, timeline
        )
    except Exception as exc:
        _log.warning("[INVESTIGATE] RCA failed: %s", exc)
        rca = RootCauseAnalysis(
            root_cause=hypotheses[0].cause,
            confidence=hypotheses[0].confidence,
            supporting_evidence=hypotheses[0].evidence,
            historical_matches=[],
            reasoning_steps=["RCA unavailable", f"Fallback from top hypothesis: {hypotheses[0].cause}"],
        )
        recommended_action = "notify_only"
        timeline.append(_timeline_event(
            InvestigationStage.ROOT_CAUSE_ANALYSIS, f"RCA fallback: {exc}"
        ))

    # ── Stage 5: Action Planning ──────────────────────────────────────────────
    routing = _route_action(rca.confidence)
    timeline.append(_timeline_event(
        InvestigationStage.ACTION_PLANNING,
        f"Confidence={rca.confidence:.0%} → routing={routing.value} action={recommended_action}",
    ))

    llm_cost = tracker.summary() if tracker else {}

    # ── Evidence contribution scoring ─────────────────────────────────────────
    hist_refs  = rca.historical_matches or []
    mem_titles = [m.get("title", "") for m in (similar or [])]
    memories_used_count = sum(
        1 for title in mem_titles
        if title and any(title[:40].lower() in ref.lower() for ref in hist_refs)
    )
    ev_contribution = _score_evidence_contribution(evidence, rca, similar, memories_used_count)

    # ── Persist Investigation ─────────────────────────────────────────────────
    await _persist_investigation(
        inv_id, org_id, agent_id, alert.id,
        evidence, similar, hypotheses, rca, recommended_action, routing, timeline,
        retrieval_telemetry, llm_cost, ev_contribution,
    )

    # ── Save to Incident Memory ───────────────────────────────────────────────
    memory_id: str | None = None
    try:
        metrics_snap = {
            "cpu": cpu, "memory": memory, "disk": disk,
            "load_avg_1m": evidence.load_avg_1m,
            "swap_percent": evidence.swap_percent,
        }
        mem_entry = await MemoryStore.save(
            db,
            org_id=org_id,
            title=alert.title,
            severity=alert.severity,
            category=evidence.incident_type,
            metrics_snapshot=metrics_snap,
            root_cause=rca.root_cause,
            reasoning="\n".join(rca.reasoning_steps),
            hypotheses=[h.model_dump() for h in hypotheses],
            recommended_action=recommended_action,
            alert_id=alert.id,
            agent_id=agent_id,
        )
        memory_id = mem_entry.id
    except Exception as exc:
        _log.warning("[INVESTIGATE] Could not save incident memory: %s", exc)

    _log.info(
        "[INVESTIGATE] Completed %s confidence=%.2f routing=%s action=%s "
        "llm_calls=%d tokens~%d total_ms=%.0f",
        inv_id, rca.confidence, routing.value, recommended_action,
        llm_cost.get("llm_calls", 0),
        llm_cost.get("est_tokens", 0),
        llm_cost.get("total_llm_ms", 0),
    )

    return InvestigationResult(
        investigation_id=inv_id,
        agent_id=agent_id,
        alert_id=alert.id,
        evidence=evidence,
        similar_incidents=similar,
        hypotheses=hypotheses,
        root_cause=rca,
        recommended_action=recommended_action,
        confidence=rca.confidence,
        action_routing=routing,
        timeline=timeline,
        memory_id=memory_id,
        llm_cost=llm_cost,
        evidence_contribution=ev_contribution,
    )


def _minimal_result(
    inv_id: str, agent_id: str, alert_id: str | None,
    cpu: float, memory: float, disk: float,
) -> InvestigationResult:
    """Emergency fallback result when all stages fail."""
    incident_type = "cpu" if cpu >= 85 else ("memory" if memory >= 85 else "disk")
    return InvestigationResult(
        investigation_id=inv_id,
        agent_id=agent_id,
        alert_id=alert_id,
        evidence=Evidence(
            incident_type=incident_type,
            cpu=cpu, memory=memory, disk=disk,
            collection_note="Emergency fallback",
        ),
        root_cause=RootCauseAnalysis(
            root_cause="Investigation failed — metrics indicate resource pressure",
            confidence=0.40,
            supporting_evidence=[f"cpu={cpu:.1f}%", f"memory={memory:.1f}%"],
            historical_matches=[],
            reasoning_steps=["Investigation pipeline failed", "Using minimal fallback"],
        ),
        recommended_action="notify_only",
        confidence=0.40,
        action_routing=ActionRouting.INVESTIGATION_ONLY,
        timeline=[_timeline_event("FAILED", "Investigation pipeline failed")],
    )
