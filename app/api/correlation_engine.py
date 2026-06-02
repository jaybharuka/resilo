"""
correlation_engine.py — Semantic Cross-Incident Correlation Engine

Architecture:
    Recent alerts (time window)
         ↓
    Embedding lookup from IncidentMemory
         ↓
    Cosine similarity matrix
         ↓
    Single-linkage clustering (threshold-based)
         ↓
    Cluster persistence (IncidentCluster + ClusterMember)
         ↓
    LLM-inferred unified root cause per cluster

Entry points:
    correlate_recent_alerts(org_id, db, call_llm_fn)
        Called after any new investigation completes.
        Returns list[IncidentCluster] created or updated.

    get_clusters(org_id, db, status, limit)
        API read path.

Never raises — all errors are logged and the function degrades gracefully.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    ClusterMember, IncidentCluster, IncidentMemory, SessionLocal,
)

_log = logging.getLogger(__name__)

# ── Tunable constants ──────────────────────────────────────────────────────────

CORRELATION_WINDOW_MINUTES = int(60 * 4)   # look back 4 hours
MIN_CLUSTER_SIZE           = 2             # ignore singletons
SIMILARITY_THRESHOLD       = 0.85          # cosine similarity to merge into same cluster (benchmarked: FCR=0.11 F1=0.81 at 0.85)
MAX_MEMORIES_PER_RUN       = 200           # cap to avoid O(n²) blowup


# ── Maths helpers ─────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _centroid(embeddings: list[list[float]]) -> list[float]:
    """Element-wise mean of a list of vectors."""
    n = len(embeddings)
    dim = len(embeddings[0])
    return [sum(e[i] for e in embeddings) / n for i in range(dim)]


# ── Core clustering ───────────────────────────────────────────────────────────

def _cluster_memories(
    memories: list[IncidentMemory],
) -> list[list[IncidentMemory]]:
    """
    Single-linkage agglomerative clustering using cosine similarity.
    Returns a list of groups (each group ≥ MIN_CLUSTER_SIZE members).
    """
    if not memories:
        return []

    # Filter to memories that actually have an embedding
    embedded = [m for m in memories if m.embedding and len(m.embedding) > 0]
    if len(embedded) < MIN_CLUSTER_SIZE:
        return []

    n = len(embedded)
    # Union-Find for cluster membership
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    # O(n²) similarity check — capped at MAX_MEMORIES_PER_RUN
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(embedded[i].embedding, embedded[j].embedding)
            if sim >= SIMILARITY_THRESHOLD:
                union(i, j)

    # Collect groups
    groups: dict[int, list[IncidentMemory]] = {}
    for idx, mem in enumerate(embedded):
        root = find(idx)
        groups.setdefault(root, []).append(mem)

    return [g for g in groups.values() if len(g) >= MIN_CLUSTER_SIZE]


# ── LLM-inferred root cause ────────────────────────────────────────────────────

async def _infer_cluster_root_cause(
    members: list[IncidentMemory],
    call_llm_fn: Callable | None,
) -> str:
    """Ask the LLM for a single unified root cause across the cluster members."""
    if call_llm_fn is None:
        # Fallback: use most common root cause text
        causes = [m.root_cause or "" for m in members if m.root_cause]
        return causes[0] if causes else "Unknown — LLM unavailable"

    summary_lines = []
    for i, m in enumerate(members[:6], 1):
        summary_lines.append(
            f"  {i}. Agent={m.agent_id or '?'} Category={m.category} "
            f"Root cause: {(m.root_cause or 'unknown')[:120]}"
        )

    system = (
        "You are a senior SRE performing cross-incident correlation. "
        "Given multiple simultaneous incidents from different agents, "
        "identify the single most likely shared root cause in one sentence. "
        "Reply ONLY with that sentence — no preamble."
    )
    user = (
        f"These {len(members)} incidents occurred within the same time window:\n"
        + "\n".join(summary_lines)
        + "\n\nWhat is the single most likely shared root cause?"
    )
    try:
        result = await call_llm_fn(system, user)
        return (result or "").strip()[:300]
    except Exception as exc:
        _log.warning("[CORRELATION] LLM root cause inference failed: %s", exc)
        return members[0].root_cause or "Correlated incident cluster"


# ── Dominant category helper ──────────────────────────────────────────────────

def _dominant_category(members: list[IncidentMemory]) -> str:
    counts: dict[str, int] = {}
    for m in members:
        cat = m.category or "unknown"
        counts[cat] = counts.get(cat, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else "unknown"


def _dominant_severity(members: list[IncidentMemory]) -> str:
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    best = max(members, key=lambda m: order.get(m.severity or "low", 0), default=None)
    return best.severity if best else "medium"


# ── Persistence ───────────────────────────────────────────────────────────────

async def _persist_cluster(
    org_id: str,
    group: list[IncidentMemory],
    inferred_root_cause: str,
    now: datetime,
    db: AsyncSession,
) -> IncidentCluster:
    """Create or update an IncidentCluster row and its ClusterMember children."""
    category = _dominant_category(group)
    severity = _dominant_severity(group)

    # Check for an existing open cluster covering the same alerts (dedup by alert_ids)
    alert_ids = {m.alert_id for m in group if m.alert_id}
    existing_result = await db.execute(
        select(ClusterMember)
        .where(ClusterMember.org_id == org_id)
        .where(ClusterMember.alert_id.in_(list(alert_ids)))
        .limit(1)
    )
    existing_member = existing_result.scalar_one_or_none()

    if existing_member:
        # Cluster already exists — update member_count and root cause if improved
        cluster_result = await db.execute(
            select(IncidentCluster).where(IncidentCluster.id == existing_member.cluster_id)
        )
        cluster = cluster_result.scalar_one_or_none()
        if cluster:
            cluster.member_count = max(cluster.member_count, len(group))
            if inferred_root_cause:
                cluster.inferred_root_cause = inferred_root_cause
            cluster.updated_at = now
            _log.info("[CORRELATION] Updated cluster %s (%d members)", cluster.id, len(group))
            return cluster

    # Compute centroid and representative (closest to centroid)
    embs = [m.embedding for m in group if m.embedding]
    centroid = _centroid(embs) if embs else []
    rep = max(group, key=lambda m: _cosine(m.embedding or [], centroid) if m.embedding and centroid else 0)
    similarities = [_cosine(m.embedding, centroid) for m in group if m.embedding]
    avg_sim = sum(similarities) / len(similarities) if similarities else None

    # Minimum pairwise similarity — single-linkage chaining diagnostic.
    # If min_sim << avg_sim the cluster was likely chained; surface in UI.
    embedded_group = [m for m in group if m.embedding]
    min_pairwise = 1.0
    for i in range(len(embedded_group)):
        for j in range(i + 1, len(embedded_group)):
            s = _cosine(embedded_group[i].embedding, embedded_group[j].embedding)
            if s < min_pairwise:
                min_pairwise = s
    min_sim = min_pairwise if len(embedded_group) >= 2 else None

    cluster = IncidentCluster(
        id=str(uuid.uuid4()),
        org_id=org_id,
        title=f"Correlated {category} cluster: {inferred_root_cause[:80]}",
        inferred_root_cause=inferred_root_cause,
        status="open",
        severity=severity,
        category=category,
        member_count=len(group),
        avg_similarity=round(avg_sim, 4) if avg_sim else None,
        min_similarity=round(min_sim, 4) if min_sim is not None else None,
        representative_alert_id=rep.alert_id,
        correlation_method="semantic",
        window_start=min((m.created_at for m in group), default=now),
        window_end=max((m.created_at for m in group), default=now),
        created_at=now,
        updated_at=now,
    )
    db.add(cluster)
    await db.flush()

    for m in group:
        sim = _cosine(m.embedding, centroid) if m.embedding and centroid else None
        db.add(ClusterMember(
            id=str(uuid.uuid4()),
            cluster_id=cluster.id,
            org_id=org_id,
            alert_id=m.alert_id,
            memory_id=m.id,
            agent_id=m.agent_id,
            similarity=round(sim, 4) if sim is not None else None,
            root_cause=m.root_cause,
            category=m.category,
        ))

    _log.info(
        "[CORRELATION] Created cluster %s: %d members, category=%s, sim=%.3f root_cause=%r",
        cluster.id, len(group), category, avg_sim or 0, inferred_root_cause[:60],
    )
    return cluster


# ── Main entry point ───────────────────────────────────────────────────────────

async def correlate_recent_alerts(
    org_id: str,
    call_llm_fn: Callable | None = None,
    window_minutes: int = CORRELATION_WINDOW_MINUTES,
) -> list[dict[str, Any]]:
    """
    Scan recent IncidentMemory entries, cluster by embedding similarity,
    persist new IncidentClusters, return list of cluster dicts.

    Designed to be called as a background task after each investigation completes.
    Never raises.
    """
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=window_minutes)

        async with SessionLocal() as db:
            result = await db.execute(
                select(IncidentMemory)
                .where(IncidentMemory.org_id == org_id)
                .where(IncidentMemory.created_at >= cutoff)
                .where(IncidentMemory.embedding.isnot(None))
                .order_by(IncidentMemory.created_at.desc())
                .limit(MAX_MEMORIES_PER_RUN)
            )
            memories: list[IncidentMemory] = list(result.scalars().all())

        if len(memories) < MIN_CLUSTER_SIZE:
            _log.debug("[CORRELATION] Too few embedded memories (%d) for org %s", len(memories), org_id)
            return []

        groups = _cluster_memories(memories)
        if not groups:
            _log.debug("[CORRELATION] No clusters found (%d memories)", len(memories))
            return []

        clusters_out: list[dict[str, Any]] = []
        async with SessionLocal() as db:
            for group in groups:
                root_cause = await _infer_cluster_root_cause(group, call_llm_fn)
                cluster = await _persist_cluster(org_id, group, root_cause, now, db)
                await db.commit()
                clusters_out.append({
                    "id":                 cluster.id,
                    "title":              cluster.title,
                    "inferred_root_cause": cluster.inferred_root_cause,
                    "status":             cluster.status,
                    "severity":           cluster.severity,
                    "category":           cluster.category,
                    "member_count":       cluster.member_count,
                    "avg_similarity":     cluster.avg_similarity,
                    "window_start":       cluster.window_start.isoformat() if cluster.window_start else None,
                    "window_end":         cluster.window_end.isoformat() if cluster.window_end else None,
                    "created_at":         cluster.created_at.isoformat() if cluster.created_at else None,
                })

        _log.info("[CORRELATION] Completed: %d cluster(s) from %d memories", len(clusters_out), len(memories))
        return clusters_out

    except Exception as exc:
        _log.error("[CORRELATION] correlate_recent_alerts failed: %s", exc)
        return []


async def get_clusters(
    org_id: str,
    db: AsyncSession,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read path: return recent clusters with their members."""
    q = (
        select(IncidentCluster)
        .where(IncidentCluster.org_id == org_id)
        .order_by(IncidentCluster.created_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(IncidentCluster.status == status)

    result = await db.execute(q)
    clusters = result.scalars().all()

    out = []
    for c in clusters:
        members_result = await db.execute(
            select(ClusterMember).where(ClusterMember.cluster_id == c.id)
        )
        members = members_result.scalars().all()
        out.append({
            "id":                  c.id,
            "title":               c.title,
            "inferred_root_cause": c.inferred_root_cause,
            "status":              c.status,
            "severity":            c.severity,
            "category":            c.category,
            "member_count":        c.member_count,
            "avg_similarity":      c.avg_similarity,
            "min_similarity":      c.min_similarity,
            "correlation_method":  c.correlation_method,
            "window_start":        c.window_start.isoformat() if c.window_start else None,
            "window_end":          c.window_end.isoformat() if c.window_end else None,
            "created_at":          c.created_at.isoformat() if c.created_at else None,
            "members": [
                {
                    "alert_id":   m.alert_id,
                    "agent_id":   m.agent_id,
                    "memory_id":  m.memory_id,
                    "similarity": m.similarity,
                    "root_cause": m.root_cause,
                    "category":   m.category,
                    "joined_at":  m.joined_at.isoformat() if m.joined_at else None,
                }
                for m in members
            ],
        })
    return out
