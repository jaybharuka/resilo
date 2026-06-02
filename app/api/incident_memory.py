"""
incident_memory.py — Historical incident knowledge base.

Stores every completed AI investigation as a searchable memory entry.
Retrieved before each LLM call to inject relevant historical context,
improving root-cause accuracy without RAG or vector embeddings.

Public API:
    save_incident_memory()     — persist a completed investigation
    find_similar_incidents()   — scored similarity search (top-N)
    build_memory_context()     — format matches into an LLM prompt block
    mark_memory_outcome()      — update executed_action + success after execution
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import IncidentMemory, SessionLocal

_log = logging.getLogger(__name__)

# ── Keyword extraction ────────────────────────────────────────────────────────

_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "in", "on", "at", "to", "of", "and", "or",
    "for", "with", "by", "from", "was", "be", "are", "has", "had", "have",
    "this", "that", "it", "its", "above", "below", "due", "high", "low",
})


def _extract_tags(root_cause: str, category: str, severity: str) -> list[str]:
    """Extract searchable keyword tags from free-text root cause."""
    words = re.findall(r"[a-z]+", (root_cause or "").lower())
    tags = [w for w in words if len(w) > 3 and w not in _STOP_WORDS]
    tags.append(category.lower())
    tags.append(severity.lower())
    return list(dict.fromkeys(tags))[:20]  # deduplicate, cap at 20


def _metric_bucket(value: float | None) -> str:
    """Map a metric percentage to a named range bucket for coarse matching."""
    if value is None:
        return "unknown"
    if value >= 95:
        return "critical"
    if value >= 85:
        return "high"
    if value >= 70:
        return "elevated"
    if value >= 50:
        return "moderate"
    return "normal"


# ── Similarity scoring ────────────────────────────────────────────────────────

def _similarity_score(
    candidate: IncidentMemory,
    category: str,
    severity: str,
    metrics: dict[str, Any],
    query_tags: list[str],
) -> float:
    """
    Score a historical IncidentMemory against the current incident context.
    Returns 0.0–1.0 (higher = more similar).

    Weights:
      - Category match:         0.30
      - Metric bucket match:    0.30
      - Tag overlap:            0.25
      - Severity match:         0.10
      - Had successful fix:     0.05
    """
    score = 0.0

    # Category match
    if (candidate.category or "").lower() == category.lower():
        score += 0.30

    # Metric bucket match (cpu + memory + disk)
    cand_metrics: dict = candidate.metrics_snapshot or {}
    matches = 0
    for field in ("cpu", "memory", "disk"):
        if _metric_bucket(metrics.get(field)) == _metric_bucket(cand_metrics.get(field)):
            matches += 1
    score += 0.30 * (matches / 3)

    # Tag overlap (Jaccard-like)
    cand_tags: set[str] = set(candidate.tags or [])
    query_set: set[str] = set(query_tags)
    if query_set:
        overlap = len(cand_tags & query_set) / len(cand_tags | query_set)
        score += 0.25 * overlap

    # Severity match
    if (candidate.severity or "").lower() == severity.lower():
        score += 0.10

    # Bonus: the historical incident had a confirmed successful fix
    if candidate.success is True:
        score += 0.05

    return round(score, 4)


# ── Public API ────────────────────────────────────────────────────────────────

async def save_incident_memory(
    db: AsyncSession,
    *,
    org_id: str,
    title: str,
    severity: str,
    category: str,
    metrics_snapshot: dict[str, Any],
    root_cause: str,
    reasoning: str,
    hypotheses: list[dict],
    recommended_action: str,
    incident_id: str | None = None,
    alert_id: str | None = None,
    agent_id: str | None = None,
    executed_action: str | None = None,
    success: bool | None = None,
    resolution_time: float | None = None,
) -> IncidentMemory:
    """Persist one investigation outcome to the knowledge base.

    Safe to call from a background task — uses the passed session.
    """
    tags = _extract_tags(root_cause, category, severity)
    entry = IncidentMemory(
        id=str(uuid.uuid4()),
        org_id=org_id,
        incident_id=incident_id,
        alert_id=alert_id,
        agent_id=agent_id,
        title=title,
        severity=severity,
        category=category,
        metrics_snapshot=metrics_snapshot,
        root_cause=root_cause,
        reasoning=reasoning,
        hypotheses=hypotheses,
        recommended_action=recommended_action,
        executed_action=executed_action,
        success=success,
        resolution_time=resolution_time,
        tags=tags,
    )
    db.add(entry)
    await db.flush()
    _log.info("[MEMORY] Saved incident_memory id=%s category=%s severity=%s",
              entry.id[:8], category, severity)
    return entry


async def find_similar_incidents(
    db: AsyncSession,
    *,
    org_id: str,
    category: str,
    severity: str,
    metrics: dict[str, Any],
    root_cause_hint: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the top-N most similar historical incidents, scored by relevance.

    Fetches up to 200 recent memories for this org and scores them locally.
    No vector embeddings required.
    """
    result = await db.execute(
        select(IncidentMemory)
        .where(IncidentMemory.org_id == org_id)
        .order_by(desc(IncidentMemory.created_at))
        .limit(200)
    )
    candidates = result.scalars().all()
    if not candidates:
        return []

    query_tags = _extract_tags(root_cause_hint, category, severity)
    scored: list[tuple[float, IncidentMemory]] = []
    for c in candidates:
        s = _similarity_score(c, category, severity, metrics, query_tags)
        if s > 0.05:
            scored.append((s, c))

    scored.sort(key=lambda t: t[0], reverse=True)

    return [
        {
            "memory_id":          m.id,
            "similarity_score":   score,
            "title":              m.title,
            "category":           m.category,
            "severity":           m.severity,
            "root_cause":         m.root_cause or "",
            "recommended_action": m.recommended_action or "",
            "executed_action":    m.executed_action,
            "success":            m.success,
            "resolution_time":    m.resolution_time,
            "metrics_snapshot":   m.metrics_snapshot or {},
            "created_at":         m.created_at.isoformat() if m.created_at else None,
        }
        for score, m in scored[:limit]
    ]


def build_memory_context(similar: list[dict[str, Any]]) -> str:
    """Format similar incidents into a structured LLM prompt block."""
    if not similar:
        return "HISTORICAL MATCHES:\n  (no similar incidents found in memory)\n"

    lines = ["HISTORICAL MATCHES (most relevant first):"]
    for i, m in enumerate(similar, 1):
        score_pct = int(m["similarity_score"] * 100)
        outcome = "✓ Resolved" if m["success"] is True else ("✗ Failed" if m["success"] is False else "? Unknown")
        rt = f"{m['resolution_time']:.0f}s" if m["resolution_time"] else "unknown"
        lines.append(f"\n  [{i}] {m['title']} (similarity={score_pct}%)")
        lines.append(f"      Root cause:  {m['root_cause']}")
        lines.append(f"      Action taken: {m['executed_action'] or m['recommended_action']}")
        lines.append(f"      Outcome:      {outcome}  (resolved in {rt})")
        snap = m.get("metrics_snapshot") or {}
        if snap:
            lines.append(
                f"      Metrics at time: cpu={snap.get('cpu', '?')}%  "
                f"mem={snap.get('memory', '?')}%  disk={snap.get('disk', '?')}%"
            )

    lines.append("")
    return "\n".join(lines)


async def mark_memory_outcome(
    db: AsyncSession,
    *,
    memory_id: str,
    executed_action: str,
    success: bool,
    resolution_time: float | None = None,
) -> None:
    """Update a memory entry after an action completes so future searches reflect outcomes."""
    result = await db.execute(
        select(IncidentMemory).where(IncidentMemory.id == memory_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return
    entry.executed_action = executed_action
    entry.success = success
    if resolution_time is not None:
        entry.resolution_time = resolution_time
    entry.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    _log.info("[MEMORY] Updated outcome for memory_id=%s action=%s success=%s",
              memory_id[:8], executed_action, success)
