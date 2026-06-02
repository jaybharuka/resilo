"""
memory_store.py — Semantic incident memory with Gemini embeddings.

Provides a MemoryStore abstraction that can be swapped to pgvector / Qdrant
/ Pinecone later without touching investigation_engine.py.

Current backend:
  - Embeddings: Gemini text-embedding-004 via REST (reuses GEMINI_API_KEY)
  - Storage: IncidentMemory.embedding (JSON float[] column)
  - Retrieval: cosine_similarity() in Python over fetched candidates

Public API:
    MemoryStore.embed_text()         — generate embedding for any string
    MemoryStore.save()               — persist memory + embedding
    MemoryStore.search()             — semantic top-k search with telemetry
    MemoryStore.update_outcome()     — update executed_action + success

Keyword fallback:
    If the Gemini embed call fails, search() falls back to the legacy
    keyword-bucket scorer in incident_memory.py so investigations
    always complete even without network access.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.incident_memory import (
    _extract_tags,
    _similarity_score,
    build_memory_context,
)
from app.core.database import IncidentMemory

_log = logging.getLogger(__name__)

# ── Embedding model constants ─────────────────────────────────────────────────

_EMBED_MODEL       = "gemini-embedding-001"
_EMBED_DIM         = 768          # text-embedding-004 output dimension
_EMBED_TIMEOUT     = 10.0         # seconds
_COSINE_THRESHOLD  = 0.70         # minimum cosine similarity to surface a hit
_CANDIDATE_LIMIT   = 500          # max rows pulled from DB before scoring


# ── Cosine similarity ─────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return round(dot / (mag_a * mag_b), 6)


# ── Text canonicalisation ─────────────────────────────────────────────────────

def _build_embed_text(
    root_cause: str,
    category: str,
    severity: str,
    metrics: dict[str, Any] | None = None,
    action: str | None = None,
    outcome: str | None = None,
) -> str:
    """
    Produce a single string that captures the key semantics of an incident.
    This is what gets embedded — consistent format is critical.
    """
    parts = [
        f"Incident type: {category}",
        f"Severity: {severity}",
        f"Root cause: {root_cause or 'unknown'}",
    ]
    if action:
        parts.append(f"Action taken: {action}")
    if outcome:
        parts.append(f"Outcome: {outcome}")
    if metrics:
        cpu  = metrics.get("cpu")
        mem  = metrics.get("memory")
        disk = metrics.get("disk")
        if cpu  is not None: parts.append(f"CPU: {cpu:.1f}%")
        if mem  is not None: parts.append(f"Memory: {mem:.1f}%")
        if disk is not None: parts.append(f"Disk: {disk:.1f}%")
    return ". ".join(parts)


# ── Gemini embedding call ─────────────────────────────────────────────────────

async def embed_text(text: str) -> list[float] | None:
    """
    Call Gemini text-embedding-004 and return the embedding vector.
    Returns None on failure — callers must handle gracefully.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        _log.debug("[EMBED] GEMINI_API_KEY not set — skipping embedding")
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_EMBED_MODEL}:embedContent?key={api_key}"
    )
    payload = {
        "model": f"models/{_EMBED_MODEL}",
        "content": {"parts": [{"text": text[:8000]}]},   # API max ~10k chars
        "taskType": "SEMANTIC_SIMILARITY",
    }

    try:
        async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            vector: list[float] = data["embedding"]["values"]
            return vector
    except Exception as exc:
        _log.warning("[EMBED] Gemini embed call failed: %s", exc)
        return None


# ── MemoryStore ───────────────────────────────────────────────────────────────

class MemoryStore:
    """
    Abstraction layer over incident memory retrieval.

    Current backend: Gemini embeddings + cosine similarity in Python.
    Drop-in replacement backend (future): pgvector / Qdrant / Pinecone —
    only this class needs changing; investigation_engine.py is unaffected.
    """

    # ── save ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def save(
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
        """
        Persist one investigation to the knowledge base and generate its embedding.

        Embedding is generated asynchronously; on failure the row is saved
        without an embedding (keyword fallback still works).
        """
        tags = _extract_tags(root_cause, category, severity)

        # Generate embedding for semantic retrieval
        embed_text_str = _build_embed_text(
            root_cause=root_cause,
            category=category,
            severity=severity,
            metrics=metrics_snapshot,
            action=executed_action or recommended_action,
            outcome="resolved" if success is True else ("failed" if success is False else None),
        )
        vector = await embed_text(embed_text_str)

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
            embedding=vector,
            embedding_model=_EMBED_MODEL if vector else None,
            embedding_created_at=datetime.now(timezone.utc) if vector else None,
        )
        db.add(entry)
        await db.flush()
        _log.info(
            "[MEMORY] Saved id=%s category=%s embedded=%s",
            entry.id[:8], category, vector is not None,
        )
        return entry

    # ── search ────────────────────────────────────────────────────────────────

    @staticmethod
    async def search(
        db: AsyncSession,
        *,
        org_id: str,
        category: str,
        severity: str,
        metrics: dict[str, Any],
        root_cause_hint: str = "",
        limit: int = 5,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Semantic top-k incident search.

        Returns:
            (matches, telemetry)

            matches   — list of dicts (same schema as incident_memory.find_similar_incidents)
            telemetry — {semantic_hits, avg_similarity, retrieval_time_ms, method}

        Method: "semantic" if embeddings available, "keyword" fallback otherwise.
        """
        t0 = time.monotonic()

        # Build query embedding
        query_text = _build_embed_text(
            root_cause=root_cause_hint,
            category=category,
            severity=severity,
            metrics=metrics,
        )
        query_vec = await embed_text(query_text)

        # Fetch recent candidates from DB
        result = await db.execute(
            select(IncidentMemory)
            .where(IncidentMemory.org_id == org_id)
            .order_by(desc(IncidentMemory.created_at))
            .limit(_CANDIDATE_LIMIT)
        )
        candidates = result.scalars().all()

        elapsed_ms = (time.monotonic() - t0) * 1000

        if not candidates:
            return [], {
                "semantic_hits": 0, "avg_similarity": None,
                "retrieval_time_ms": round(elapsed_ms, 1), "method": "none",
            }

        # ── Semantic path: both query and candidates have embeddings ──────────
        embed_candidates = [c for c in candidates if c.embedding]

        if query_vec is not None and embed_candidates:
            scored: list[tuple[float, IncidentMemory]] = []
            for c in embed_candidates:
                sim = cosine_similarity(query_vec, c.embedding)
                if sim >= _COSINE_THRESHOLD:
                    scored.append((sim, c))

            # Also score non-embedded candidates with keyword fallback
            keyword_only = [c for c in candidates if not c.embedding]
            if keyword_only:
                query_tags = _extract_tags(root_cause_hint, category, severity)
                for c in keyword_only:
                    s = _similarity_score(c, category, severity, metrics, query_tags)
                    if s > 0.10:
                        scored.append((s, c))

            scored.sort(key=lambda t: t[0], reverse=True)
            top = scored[:limit]

            sims = [s for s, _ in top]
            telemetry = {
                "semantic_hits":      len([s for s, _ in scored]),
                "avg_similarity":     round(sum(sims) / len(sims), 4) if sims else None,
                "retrieval_time_ms":  round((time.monotonic() - t0) * 1000, 1),
                "method":             "semantic",
            }

        else:
            # ── Keyword fallback (no embeddings) ─────────────────────────────
            query_tags = _extract_tags(root_cause_hint, category, severity)
            scored = []
            for c in candidates:
                s = _similarity_score(c, category, severity, metrics, query_tags)
                if s > 0.05:
                    scored.append((s, c))
            scored.sort(key=lambda t: t[0], reverse=True)
            top = scored[:limit]

            sims = [s for s, _ in top]
            telemetry = {
                "semantic_hits":      0,
                "avg_similarity":     round(sum(sims) / len(sims), 4) if sims else None,
                "retrieval_time_ms":  round((time.monotonic() - t0) * 1000, 1),
                "method":             "keyword",
            }

        matches = [
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
                "has_embedding":      m.embedding is not None,
                "created_at":         m.created_at.isoformat() if m.created_at else None,
            }
            for score, m in top
        ]

        return matches, telemetry

    # ── update_outcome ────────────────────────────────────────────────────────

    @staticmethod
    async def update_outcome(
        db: AsyncSession,
        *,
        memory_id: str,
        executed_action: str,
        success: bool,
        resolution_time: float | None = None,
    ) -> None:
        """Update a memory entry after execution outcome is known."""
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

        # Re-embed with outcome so future retrievals account for outcome quality
        embed_text_str = _build_embed_text(
            root_cause=entry.root_cause or "",
            category=entry.category,
            severity=entry.severity,
            metrics=entry.metrics_snapshot,
            action=executed_action,
            outcome="resolved" if success else "failed",
        )
        new_vec = await embed_text(embed_text_str)
        if new_vec:
            entry.embedding = new_vec
            entry.embedding_created_at = datetime.now(timezone.utc)

        await db.flush()
        _log.info("[MEMORY] Updated outcome id=%s action=%s success=%s re_embedded=%s",
                  memory_id[:8], executed_action, success, new_vec is not None)
