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
from app.api.incident_memory import (
    build_memory_context, find_similar_incidents, save_incident_memory,
)

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
    )

    timeline.append(_timeline_event(
        InvestigationStage.EVIDENCE_COLLECTION,
        f"Evidence collected: type={incident_type} cpu={cpu:.1f}% mem={memory:.1f}% disk={disk:.1f}%",
    ))
    return evidence, timeline


# ── Stage 2: Historical Analysis ─────────────────────────────────────────────

async def _historical_analysis(
    db: AsyncSession,
    org_id: str,
    evidence: Evidence,
    alert: AlertRecord,
    timeline: list[dict],
) -> tuple[list[dict], str]:
    """Retrieve similar incidents and build the memory context block."""
    timeline.append(_timeline_event(
        InvestigationStage.HISTORICAL_ANALYSIS, "Searching historical incident memory"
    ))

    metrics_dict = {
        "cpu": evidence.cpu,
        "memory": evidence.memory,
        "disk": evidence.disk,
    }
    similar = await find_similar_incidents(
        db,
        org_id=org_id,
        category=evidence.incident_type,
        severity=alert.severity,
        metrics=metrics_dict,
        root_cause_hint=alert.detail or "",
        limit=5,
    )

    n = len(similar)
    timeline.append(_timeline_event(
        InvestigationStage.HISTORICAL_ANALYSIS,
        f"Found {n} similar historical incident(s)" if n else "No similar incidents in memory",
    ))

    memory_context = build_memory_context(similar)
    return similar, memory_context


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
) -> None:
    """Upsert Investigation row into DB."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Investigation).where(Investigation.id == inv_id)
            )
            inv = result.scalar_one_or_none()
            if inv is None:
                inv = Investigation(id=inv_id, org_id=org_id, agent_id=agent_id)
                db.add(inv)

            inv.alert_id           = alert_id
            inv.status             = "completed"
            inv.stage              = "ACTION_PLANNING"
            inv.evidence           = evidence.model_dump()
            inv.similar_incidents  = similar
            inv.hypotheses         = [h.model_dump() for h in hypotheses]
            inv.root_cause         = rca.model_dump()
            inv.recommended_action = recommended_action
            inv.confidence         = rca.confidence
            inv.action_routing     = routing.value
            inv.timeline           = timeline
            inv.completed_at       = datetime.now(timezone.utc)
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
            db, agent_id, org_id, cpu, memory, disk, alert, extra_metrics
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

    # ── Stage 2: Historical Analysis ─────────────────────────────────────────
    try:
        similar, memory_context = await _historical_analysis(
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

    # ── Persist Investigation ─────────────────────────────────────────────────
    await _persist_investigation(
        inv_id, org_id, agent_id, alert.id,
        evidence, similar, hypotheses, rca, recommended_action, routing, timeline,
    )

    # ── Save to Incident Memory ───────────────────────────────────────────────
    memory_id: str | None = None
    try:
        metrics_snap = {
            "cpu": cpu, "memory": memory, "disk": disk,
            "load_avg_1m": evidence.load_avg_1m,
            "swap_percent": evidence.swap_percent,
        }
        mem_entry = await save_incident_memory(
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
        "[INVESTIGATE] Completed %s confidence=%.2f routing=%s action=%s",
        inv_id, rca.confidence, routing.value, recommended_action,
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
