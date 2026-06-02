"""
investigations_api.py — REST endpoints for the investigation engine.

Routes:
  GET  /investigations                     — list recent investigations for the org
  GET  /investigations/stats               — AI observability metrics
  GET  /investigations/{id}               — get single investigation with full detail
  GET  /incidents/{incident_id}/timeline  — structured timeline for an incident
  GET  /incidents/{incident_id}/similar   — similar historical incidents from memory
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.incident_memory import find_similar_incidents
from app.api.correlation_engine import correlate_recent_alerts, get_clusters
from app.core.database import (
    Incident, IncidentCluster, IncidentMemory, Investigation, InvestigationFeedback, LogEntry, get_db,
)

router = APIRouter(tags=["investigations"])
_log = logging.getLogger(__name__)


# ── Auth helper (mirrors pattern in runtime.py / v1_api.py) ──────────────────

async def _require_token(request: Request) -> dict[str, Any]:
    """Extract and validate the JWT Bearer token from Authorization header."""
    from jose import JWTError, jwt as _jwt
    import os

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:]
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY not configured")
    try:
        payload = _jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


def _inv_to_dict(inv: Investigation) -> dict[str, Any]:
    return {
        "id":                 inv.id,
        "org_id":             inv.org_id,
        "agent_id":           inv.agent_id,
        "alert_id":           inv.alert_id,
        "incident_id":        inv.incident_id,
        "status":             inv.status,
        "stage":              inv.stage,
        "confidence":         inv.confidence,
        "recommended_action": inv.recommended_action,
        "action_routing":     inv.action_routing,
        "evidence":           inv.evidence,
        "similar_incidents":  inv.similar_incidents,
        "hypotheses":         inv.hypotheses,
        "root_cause":         inv.root_cause,
        "timeline":           inv.timeline,
        "created_at":         inv.created_at.isoformat() if inv.created_at else None,
        "completed_at":       inv.completed_at.isoformat() if inv.completed_at else None,
    }


# ── GET /investigations/stats ────────────────────────────────────────────────
# MUST be registered before /investigations/{id} so the literal "stats" is not
# treated as an investigation_id path parameter.

@router.get("/investigations/stats")
async def investigation_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    window_hours: int = Query(default=24, ge=1, le=168,
                              description="Look-back window in hours"),
) -> dict[str, Any]:
    """
    AI observability metrics for the investigation engine.

    Returns:
      - total_investigations   : count in window
      - by_status              : {completed, running, failed}
      - by_routing             : {auto_execute, manual_approval, investigation_only}
      - avg_confidence         : mean confidence across completed investigations
      - successful_fix_rate    : % where executed action resolved the incident
      - false_positive_rate    : % of investigation_only that had prior similar incident
      - avg_stage_at_failure   : stage where pipelines fail most
      - top_root_causes        : top-5 most common root cause strings
      - top_actions            : top-5 recommended actions
      - memory_entries         : total rows in incident_memory for this org
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    result = await db.execute(
        select(Investigation)
        .where(Investigation.org_id == org_id)
        .where(Investigation.created_at >= cutoff)
        .order_by(desc(Investigation.created_at))
    )
    rows: list[Investigation] = result.scalars().all()

    # ── Basic counts ──────────────────────────────────────────────────────────
    by_status: dict[str, int] = Counter(r.status for r in rows)
    by_routing: dict[str, int] = Counter(
        r.action_routing or "unknown" for r in rows if r.status == "completed"
    )

    # ── Confidence ───────────────────────────────────────────────────────────
    completed = [r for r in rows if r.status == "completed"]
    confidences = [r.confidence for r in completed if r.confidence is not None]
    avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None

    # ── Successful fix rate (from IncidentMemory) ─────────────────────────────
    mem_result = await db.execute(
        select(IncidentMemory)
        .where(IncidentMemory.org_id == org_id)
        .where(IncidentMemory.created_at >= cutoff)
    )
    mem_rows: list[IncidentMemory] = mem_result.scalars().all()

    resolved   = sum(1 for m in mem_rows if m.success is True)
    unresolved = sum(1 for m in mem_rows if m.success is False)
    total_with_outcome = resolved + unresolved
    successful_fix_rate = (
        round(resolved / total_with_outcome, 3) if total_with_outcome > 0 else None
    )

    # ── False positive rate proxy ─────────────────────────────────────────────
    # investigations_only where similar_incidents > 0 (known pattern, still low conf)
    inv_only = [r for r in rows if r.action_routing == "investigation_only"]
    fp_candidates = sum(
        1 for r in inv_only
        if r.similar_incidents and len(r.similar_incidents) > 0
    )
    false_positive_rate = (
        round(fp_candidates / len(inv_only), 3) if inv_only else None
    )

    # ── Stage at failure ──────────────────────────────────────────────────────
    failed = [r for r in rows if r.status == "failed"]
    stage_counts: dict[str, int] = Counter(r.stage for r in failed if r.stage)

    # ── Top root causes ───────────────────────────────────────────────────────
    root_causes: list[str] = []
    for r in completed:
        if r.root_cause and isinstance(r.root_cause, dict):
            rc = r.root_cause.get("root_cause", "")
            if rc:
                root_causes.append(rc[:120])   # truncate long strings
    top_root_causes = [
        {"root_cause": rc, "count": cnt}
        for rc, cnt in Counter(root_causes).most_common(5)
    ]

    # ── Top recommended actions ───────────────────────────────────────────────
    actions = [r.recommended_action for r in completed if r.recommended_action]
    top_actions = [
        {"action": a, "count": cnt}
        for a, cnt in Counter(actions).most_common(5)
    ]

    # ── Evidence quality ─────────────────────────────────────────────────────
    inv_with_logs = [
        r for r in completed
        if isinstance(r.evidence, dict) and r.evidence.get("log_line_count", 0) > 0
    ]
    inv_with_errors = [
        r for r in completed
        if isinstance(r.evidence, dict) and r.evidence.get("error_line_count", 0) > 0
    ]
    inv_with_log_summary = [
        r for r in completed
        if isinstance(r.evidence, dict) and r.evidence.get("log_summary")
    ]

    total_logs_collected = sum(
        r.evidence.get("log_line_count", 0) for r in completed
        if isinstance(r.evidence, dict)
    )
    total_errors_detected = sum(
        r.evidence.get("error_line_count", 0) for r in completed
        if isinstance(r.evidence, dict)
    )

    # ── Memory bank size ─────────────────────────────────────────────────────
    mem_count_result = await db.execute(
        select(func.count()).where(IncidentMemory.org_id == org_id)
    )
    memory_entries = mem_count_result.scalar() or 0

    # ── Embedding coverage ────────────────────────────────────────────────────
    embed_count_result = await db.execute(
        select(func.count())
        .where(IncidentMemory.org_id == org_id)
        .where(IncidentMemory.embedding.isnot(None))
    )
    embedded_entries = embed_count_result.scalar() or 0

    # ── Root cause accuracy (from feedback) ───────────────────────────────────
    fb_result = await db.execute(
        select(InvestigationFeedback)
        .where(InvestigationFeedback.org_id == org_id)
        .where(InvestigationFeedback.created_at >= cutoff)
    )
    fb_rows: list[InvestigationFeedback] = fb_result.scalars().all()

    total_fb      = len(fb_rows)
    fb_correct    = sum(1 for f in fb_rows if f.correct is True)
    fb_incorrect  = sum(1 for f in fb_rows if f.correct is False)
    overall_accuracy = (
        round(fb_correct / (fb_correct + fb_incorrect), 3)
        if (fb_correct + fb_incorrect) > 0 else None
    )

    # Accuracy by incident type
    by_type: dict[str, dict] = {}
    for f in fb_rows:
        t = f.incident_type or "unknown"
        rec = by_type.setdefault(t, {"total": 0, "correct": 0})
        rec["total"] += 1
        if f.correct is True:
            rec["correct"] += 1
    accuracy_by_type = {
        t: round(v["correct"] / v["total"], 3) if v["total"] else None
        for t, v in by_type.items()
    }

    # Accuracy by confidence bucket
    by_bucket: dict[str, dict] = {}
    for f in fb_rows:
        b = f.confidence_bucket or "unknown"
        rec = by_bucket.setdefault(b, {"total": 0, "correct": 0})
        rec["total"] += 1
        if f.correct is True:
            rec["correct"] += 1
    accuracy_by_confidence = {
        b: round(v["correct"] / v["total"], 3) if v["total"] else None
        for b, v in by_bucket.items()
    }

    # ── Semantic retrieval metrics ────────────────────────────────────────────
    semantic_rows = [r for r in completed if r.semantic_hits is not None]
    avg_semantic_hits = (
        round(sum(r.semantic_hits for r in semantic_rows) / len(semantic_rows), 2)
        if semantic_rows else None
    )
    sims_all = [r.avg_similarity for r in completed if r.avg_similarity is not None]
    avg_retrieval_similarity = round(sum(sims_all) / len(sims_all), 4) if sims_all else None
    rt_all = [r.retrieval_time_ms for r in completed if r.retrieval_time_ms is not None]
    avg_retrieval_ms = round(sum(rt_all) / len(rt_all), 1) if rt_all else None

    return {
        "ok":                      True,
        "window_hours":            window_hours,
        "total_investigations":    len(rows),
        "by_status":               dict(by_status),
        "by_routing":              dict(by_routing),
        "avg_confidence":          avg_confidence,
        "successful_fix_rate":     successful_fix_rate,
        "false_positive_rate":     false_positive_rate,
        "stage_at_failure":        dict(stage_counts),
        "top_root_causes":         top_root_causes,
        "top_actions":             top_actions,
        "memory_entries":          memory_entries,
        "embedded_entries":        embedded_entries,
        "embedding_coverage":      (
            round(embedded_entries / memory_entries, 3) if memory_entries else None
        ),
        "accuracy": {
            "total_feedback":          total_fb,
            "overall":                 overall_accuracy,
            "by_incident_type":        accuracy_by_type,
            "by_confidence_bucket":    accuracy_by_confidence,
        },
        "semantic_retrieval": {
            "avg_hits":                avg_semantic_hits,
            "avg_similarity":          avg_retrieval_similarity,
            "avg_retrieval_ms":        avg_retrieval_ms,
        },
        "evidence_quality": {
            "total_logs_collected":     total_logs_collected,
            "total_errors_detected":    total_errors_detected,
            "investigations_with_logs": len(inv_with_logs),
            "investigations_with_errors": len(inv_with_errors),
            "investigations_with_summary": len(inv_with_log_summary),
            "log_coverage_rate": round(
                len(inv_with_logs) / max(len(completed), 1), 3
            ),
        },
        "memory_usefulness": {
            "retrieved":   int(sum(
                len(r.similar_incidents or []) for r in completed
            )),
            "used_in_reasoning": int(sum(
                r.memories_used_in_reasoning or 0 for r in completed
                if r.memories_used_in_reasoning is not None
            )),
            "usefulness_rate": round(
                sum(r.memories_used_in_reasoning or 0 for r in completed if r.memories_used_in_reasoning is not None) /
                max(sum(len(r.similar_incidents or []) for r in completed), 1),
                3
            ),
        },
        "evidence_contribution": _aggregate_contribution(completed),
    }


def _aggregate_contribution(rows: list) -> dict[str, Any]:
    """Aggregate evidence_contribution flags across completed investigations."""
    n = len(rows)
    if n == 0:
        return {}
    contrib_rows = [r for r in rows if r.evidence_contribution]
    if not contrib_rows:
        return {"note": "no contribution data yet — run investigations first"}
    cn = len(contrib_rows)
    logs_helped    = sum(1 for r in contrib_rows if r.evidence_contribution.get("logs_helped"))
    memory_helped  = sum(1 for r in contrib_rows if r.evidence_contribution.get("memory_helped"))
    context_helped = sum(1 for r in contrib_rows if r.evidence_contribution.get("context_helped"))
    planner_helped = sum(1 for r in contrib_rows if r.evidence_contribution.get("planner_helped"))
    return {
        "investigations_scored": cn,
        "logs_helped_rate":    round(logs_helped    / cn, 3),
        "memory_helped_rate":  round(memory_helped  / cn, 3),
        "context_helped_rate": round(context_helped / cn, 3),
        "planner_helped_rate": round(planner_helped / cn, 3),
        "logs_helped_count":    logs_helped,
        "memory_helped_count":  memory_helped,
        "context_helped_count": context_helped,
        "planner_helped_count": planner_helped,
    }


# ── GET /investigations/benchmark/trends ─────────────────────────────────────

@router.get("/investigations/benchmark/trends")
async def benchmark_trends(
    request: Request,
) -> dict[str, Any]:
    """
    Serve the leaderboard.json as an API response for the Evaluation Dashboard.
    Returns the rolling benchmark history keyed by commit.
    """
    await _require_token(request)

    import pathlib, json as _json
    lb_path = pathlib.Path(__file__).parent.parent.parent / "benchmark_results" / "leaderboard.json"
    if not lb_path.exists():
        return {"ok": True, "entries": [], "note": "No benchmark runs yet. Run: python scripts/benchmark_engine.py --ab"}

    try:
        entries = _json.loads(lb_path.read_text())
    except Exception:
        return {"ok": False, "error": "Could not read leaderboard.json"}

    # Enrich with human-readable timestamps
    import datetime as _dt
    for e in entries:
        ts = e.get("timestamp")
        if ts:
            e["run_date"] = _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")

    return {
        "ok":          True,
        "entry_count": len(entries),
        "latest":      entries[-1] if entries else None,
        "entries":     entries,
    }


# ── GET /investigations/demo-runs ────────────────────────────────────────────

@router.get("/investigations/demo-runs")
async def get_demo_runs(request: Request) -> dict[str, Any]:
    """Return pre-computed demo investigation fixtures from demo_runs/."""
    await _require_token(request)
    import pathlib, json as _json
    demo_dir = pathlib.Path(__file__).parent.parent.parent / "demo_runs"
    if not demo_dir.exists():
        return {"ok": True, "runs": [], "note": "No demo_runs/ directory found"}
    runs = []
    for f in sorted(demo_dir.glob("*.json")):
        try:
            runs.append(_json.loads(f.read_text()))
        except Exception:
            pass
    return {"ok": True, "count": len(runs), "runs": runs}


# ── GET /investigations ───────────────────────────────────────────────────────

@router.get("/investigations")
async def list_investigations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, description="Filter: running|completed|failed"),
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """List recent investigations for the authenticated org."""
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    q = select(Investigation).where(Investigation.org_id == org_id)
    if status:
        q = q.where(Investigation.status == status)
    if agent_id:
        q = q.where(Investigation.agent_id == agent_id)
    q = q.order_by(desc(Investigation.created_at)).limit(limit)

    result = await db.execute(q)
    investigations = result.scalars().all()

    return {
        "ok":    True,
        "count": len(investigations),
        "items": [_inv_to_dict(inv) for inv in investigations],
    }


# ── GET /investigations/{id} ──────────────────────────────────────────────────

@router.get("/investigations/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a single investigation with all stage outputs."""
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")

    result = await db.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .where(Investigation.org_id == org_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    return {"ok": True, "investigation": _inv_to_dict(inv)}


# ── GET /investigations/{id}/explain ─────────────────────────────────────────

@router.get("/investigations/{investigation_id}/explain")
async def explain_investigation(
    investigation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Explainability dashboard for a single investigation.

    Returns a structured summary of:
      - Root cause + confidence
      - Which evidence sources were used (logs/context/memory)
      - Evidence planner steps (if planner was used)
      - Hypothesis ranking
      - Historical memory matches
      - LLM cost (calls, tokens, latency)
      - Recommended action + routing path
      - Full reasoning chain
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")

    result = await db.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .where(Investigation.org_id == org_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    evidence: dict = inv.evidence or {}
    root_cause: dict = inv.root_cause or {}
    hypotheses: list = inv.hypotheses or []
    ctx_evidence: dict = inv.context_evidence or {}
    llm_cost: dict = inv.llm_cost or {}
    ev_contribution: dict = inv.evidence_contribution or {}

    # ── Evidence sources used ─────────────────────────────────────────────────
    log_line_count    = evidence.get("log_line_count", 0)
    error_line_count  = evidence.get("error_line_count", 0)
    ctx_sections      = list(ctx_evidence.keys())
    planner_steps     = ctx_evidence.get("planner", {})
    has_memory        = bool(inv.similar_incidents)

    evidence_sources = []
    if log_line_count > 0:
        evidence_sources.append({
            "source": "logs",
            "used": True,
            "detail": f"{log_line_count} lines collected, {error_line_count} errors"
        })
    else:
        evidence_sources.append({"source": "logs", "used": False, "detail": "no logs collected"})

    static_ctx = [k for k in ctx_sections if k != "planner"]
    if static_ctx:
        evidence_sources.append({
            "source": "dynamic_context",
            "used": True,
            "detail": f"sections: {', '.join(static_ctx)}"
        })
    else:
        evidence_sources.append({"source": "dynamic_context", "used": False, "detail": "not collected"})

    if planner_steps:
        planner_section = planner_steps if isinstance(planner_steps, dict) else {}
        evidence_sources.append({
            "source": "evidence_planner",
            "used": True,
            "detail": f"{len(planner_section)} adaptive collectors run"
        })

    if has_memory:
        evidence_sources.append({
            "source": "semantic_memory",
            "used": True,
            "detail": f"{len(inv.similar_incidents)} historical matches retrieved"
        })
    else:
        evidence_sources.append({"source": "semantic_memory", "used": False, "detail": "no matches found"})

    # ── Hypothesis ranking ────────────────────────────────────────────────────
    ranked_hypotheses = sorted(
        [
            {
                "rank":       i + 1,
                "cause":      h.get("cause", ""),
                "confidence": round(float(h.get("confidence", 0)), 3),
                "evidence":   h.get("evidence", [])[:3],
            }
            for i, h in enumerate(hypotheses)
        ],
        key=lambda x: x["confidence"],
        reverse=True,
    )

    # ── Memory matches ────────────────────────────────────────────────────────
    memory_matches = [
        {
            "title":      m.get("title", ""),
            "similarity": round(float(m.get("similarity", 0)), 3),
            "root_cause": m.get("root_cause", "")[:120],
        }
        for m in (inv.similar_incidents or [])[:5]
    ]

    # ── Timeline highlights (human-readable stage names) ──────────────────────
    stage_labels = {
        "EVIDENCE_COLLECTION":   "Evidence Collection",
        "HISTORICAL_ANALYSIS":   "Historical Analysis",
        "HYPOTHESIS_GENERATION": "Hypothesis Generation",
        "ROOT_CAUSE_ANALYSIS":   "Root Cause Analysis",
        "ACTION_PLANNING":       "Action Planning",
    }
    timeline_highlights = [
        {
            "stage":  stage_labels.get(e.get("stage", ""), e.get("stage", "")),
            "event":  e.get("event", ""),
            "time":   e.get("timestamp", ""),
        }
        for e in (inv.timeline or [])
    ]

    return {
        "ok": True,
        "investigation_id": inv.id,
        "status":           inv.status,
        "root_cause": {
            "summary":              root_cause.get("root_cause", ""),
            "confidence":           round(float(root_cause.get("confidence", 0)), 3),
            "confidence_pct":       f"{root_cause.get('confidence', 0)*100:.0f}%",
            "supporting_evidence":  root_cause.get("supporting_evidence", [])[:5],
            "reasoning_steps":      root_cause.get("reasoning_steps", []),
        },
        "recommended_action":   inv.recommended_action,
        "action_routing":       inv.action_routing,
        "evidence_sources":     evidence_sources,
        "hypotheses":           ranked_hypotheses,
        "memory_matches":       memory_matches,
        "memories_used_in_reasoning": inv.memories_used_in_reasoning or 0,
        "planner_steps":        planner_steps if isinstance(planner_steps, list) else [],
        "llm_cost": {
            "calls":       llm_cost.get("llm_calls", 0),
            "est_tokens":  llm_cost.get("est_tokens", 0),
            "total_ms":    llm_cost.get("total_llm_ms", 0),
            "avg_ms":      llm_cost.get("avg_llm_ms", 0),
        },
        "timeline": timeline_highlights,
        "evidence_contribution": {
            "logs_helped":    ev_contribution.get("logs_helped",    False),
            "memory_helped":  ev_contribution.get("memory_helped",  False),
            "context_helped": ev_contribution.get("context_helped", False),
            "planner_helped": ev_contribution.get("planner_helped", False),
            "error_lines":    ev_contribution.get("error_lines",    0),
            "memory_matches": ev_contribution.get("memory_matches", 0),
            "context_sections": ev_contribution.get("context_sections", 0),
        },
        "created_at":   inv.created_at.isoformat() if inv.created_at else None,
        "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
    }


# ── GET /incidents/{incident_id}/timeline ─────────────────────────────────────

@router.get("/incidents/{incident_id}/timeline")
async def get_incident_timeline(
    incident_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return the structured AI investigation timeline for an incident.

    Merges the incident's own timeline with any linked investigation timelines
    for a complete end-to-end event log.
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")

    # Fetch the parent incident
    inc_result = await db.execute(
        select(Incident)
        .where(Incident.id == incident_id)
        .where(Incident.org_id == org_id)
    )
    incident = inc_result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Fetch linked investigations
    inv_result = await db.execute(
        select(Investigation)
        .where(Investigation.incident_id == incident_id)
        .where(Investigation.org_id == org_id)
        .order_by(Investigation.created_at)
    )
    investigations = inv_result.scalars().all()

    # Merge and sort all timeline events by timestamp
    merged: list[dict] = []

    for entry in (incident.timeline or []):
        merged.append({
            "timestamp": entry.get("ts") or entry.get("timestamp", ""),
            "source":    "incident",
            "actor":     entry.get("actor", "system"),
            "event":     entry.get("note") or entry.get("event", ""),
            "data":      entry.get("data"),
        })

    for inv in investigations:
        for entry in (inv.timeline or []):
            merged.append({
                "timestamp":        entry.get("timestamp", ""),
                "source":           "investigation",
                "investigation_id": inv.id,
                "stage":            entry.get("stage", ""),
                "event":            entry.get("event", ""),
            })

    merged.sort(key=lambda e: e.get("timestamp", ""))

    return {
        "ok":             True,
        "incident_id":    incident_id,
        "incident_status": incident.status,
        "event_count":    len(merged),
        "timeline":       merged,
    }


# ── GET /incidents/{incident_id}/similar ──────────────────────────────────────

@router.get("/incidents/{incident_id}/similar")
async def get_similar_incidents(
    incident_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """
    Find historically similar incidents from the knowledge base
    for a given incident.
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")

    inc_result = await db.execute(
        select(Incident)
        .where(Incident.id == incident_id)
        .where(Incident.org_id == org_id)
    )
    incident = inc_result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Pull metrics from the linked investigation if available
    metrics: dict = {}
    inv_result = await db.execute(
        select(Investigation)
        .where(Investigation.incident_id == incident_id)
        .where(Investigation.org_id == org_id)
        .order_by(desc(Investigation.created_at))
        .limit(1)
    )
    inv = inv_result.scalar_one_or_none()
    if inv and inv.evidence:
        ev = inv.evidence
        metrics = {
            "cpu":    ev.get("cpu", 0),
            "memory": ev.get("memory", 0),
            "disk":   ev.get("disk", 0),
        }
        category = ev.get("incident_type", "cpu")
    else:
        category = "fleet"

    similar = await find_similar_incidents(
        db,
        org_id=org_id,
        category=category,
        severity=incident.severity,
        metrics=metrics,
        root_cause_hint=incident.description,
        limit=limit,
    )

    return {
        "ok":          True,
        "incident_id": incident_id,
        "count":       len(similar),
        "similar":     similar,
    }


# ── POST /investigations/{id}/feedback ───────────────────────────────────────

@router.post("/investigations/{investigation_id}/feedback", status_code=201)
async def submit_feedback(
    investigation_id: str,
    body: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Submit root-cause accuracy feedback for an investigation.

    Body:
      correct              : bool   — was the predicted root cause accurate?
      actual_root_cause    : str    — what actually caused the incident (optional)
      action_correct       : bool   — was the recommended action appropriate? (optional)
      actual_action        : str    — action that was actually taken (optional)
      note                 : str    — freeform human note (optional)
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    # Verify investigation belongs to this org
    result = await db.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .where(Investigation.org_id == org_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    # Confidence bucket
    conf = inv.confidence or 0.0
    if conf >= 0.95:
        bucket = "high"
    elif conf >= 0.70:
        bucket = "medium"
    else:
        bucket = "low"

    # Derive incident_type from evidence
    incident_type = None
    if inv.evidence and isinstance(inv.evidence, dict):
        incident_type = inv.evidence.get("incident_type")

    fb = InvestigationFeedback(
        org_id=org_id,
        investigation_id=investigation_id,
        agent_id=inv.agent_id,
        incident_type=incident_type,
        confidence_bucket=bucket,
        predicted_root_cause=(
            inv.root_cause.get("root_cause") if isinstance(inv.root_cause, dict) else None
        ),
        actual_root_cause=body.get("actual_root_cause"),
        correct=body.get("correct"),
        predicted_action=inv.recommended_action,
        actual_action=body.get("actual_action"),
        action_correct=body.get("action_correct"),
        submitted_by=payload.get("sub", "unknown"),
        note=body.get("note"),
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)

    _log.info("[FEEDBACK] investigation=%s correct=%s", investigation_id[:12], body.get("correct"))
    return {
        "ok":              True,
        "feedback_id":     fb.id,
        "investigation_id": investigation_id,
        "correct":         fb.correct,
        "confidence_bucket": bucket,
    }


# ── GET /investigations/clusters ─────────────────────────────────────────────

@router.get("/investigations/clusters")
async def list_clusters(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None, description="Filter by status: open|investigating|resolved|dismissed"),
    limit: int = Query(default=20, le=100),
) -> dict[str, Any]:
    """Return incident clusters discovered by the semantic correlation engine."""
    payload = await _require_token(request)
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    clusters = await get_clusters(org_id, db, status=status, limit=limit)
    return {"ok": True, "count": len(clusters), "clusters": clusters}


# ── GET /investigations/clusters/{cluster_id} ─────────────────────────────────

@router.get("/investigations/clusters/{cluster_id}")
async def get_cluster(
    cluster_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a single cluster with all members."""
    payload = await _require_token(request)
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    result = await db.execute(
        select(IncidentCluster)
        .where(IncidentCluster.id == cluster_id)
        .where(IncidentCluster.org_id == org_id)
    )
    cluster = result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    clusters = await get_clusters(org_id, db, limit=1)
    match = next((c for c in clusters if c["id"] == cluster_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return {"ok": True, "cluster": match}


# ── PATCH /investigations/clusters/{cluster_id} ───────────────────────────────

@router.patch("/investigations/clusters/{cluster_id}")
async def update_cluster_status(
    cluster_id: str,
    body: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update cluster status (open → investigating → resolved | dismissed)."""
    payload = await _require_token(request)
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    result = await db.execute(
        select(IncidentCluster)
        .where(IncidentCluster.id == cluster_id)
        .where(IncidentCluster.org_id == org_id)
    )
    cluster = result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    allowed = {"open", "investigating", "resolved", "dismissed"}
    new_status = body.get("status")
    if new_status and new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")

    if new_status:
        cluster.status = new_status
        if new_status == "resolved":
            cluster.resolved_at = datetime.now(timezone.utc)
    if "inferred_root_cause" in body:
        cluster.inferred_root_cause = body["inferred_root_cause"]

    await db.commit()
    return {"ok": True, "id": cluster_id, "status": cluster.status}


# ── POST /investigations/correlate ────────────────────────────────────────────

@router.post("/investigations/correlate", status_code=202)
async def trigger_correlation(
    request: Request,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Manually trigger a correlation pass over recent alerts for this org."""
    payload = await _require_token(request)
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    window = (body or {}).get("window_minutes", 240)
    clusters = await correlate_recent_alerts(org_id, call_llm_fn=None, window_minutes=window)
    return {
        "ok": True,
        "clusters_found": len(clusters),
        "clusters": clusters,
        "window_minutes": window,
    }
