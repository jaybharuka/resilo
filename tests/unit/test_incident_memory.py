"""
Unit tests for incident_memory.py

Tests:
  - _extract_tags produces keyword tags
  - _metric_bucket returns correct range labels
  - _similarity_score weights work correctly
  - build_memory_context formats output correctly
  - save_incident_memory / find_similar_incidents (async, with mock DB)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.incident_memory import (
    _extract_tags,
    _metric_bucket,
    _similarity_score,
    build_memory_context,
)
from app.core.database import IncidentMemory


# ── Unit tests (no DB) ────────────────────────────────────────────────────────

class TestExtractTags:
    def test_filters_stop_words(self):
        tags = _extract_tags("the process is using high memory", "memory", "critical")
        assert "the" not in tags
        assert "is" not in tags
        assert "memory" in tags
        assert "critical" in tags

    def test_deduplicates(self):
        tags = _extract_tags("memory memory memory", "memory", "high")
        assert tags.count("memory") == 1

    def test_caps_at_20(self):
        long_text = " ".join(f"keyword{i}" for i in range(30))
        tags = _extract_tags(long_text, "cpu", "low")
        assert len(tags) <= 20

    def test_category_and_severity_always_present(self):
        tags = _extract_tags("", "disk", "critical")
        assert "disk" in tags
        assert "critical" in tags


class TestMetricBucket:
    def test_critical(self):
        assert _metric_bucket(97.0) == "critical"

    def test_high(self):
        assert _metric_bucket(87.0) == "high"

    def test_elevated(self):
        assert _metric_bucket(72.0) == "elevated"

    def test_moderate(self):
        assert _metric_bucket(55.0) == "moderate"

    def test_normal(self):
        assert _metric_bucket(30.0) == "normal"

    def test_none_returns_unknown(self):
        assert _metric_bucket(None) == "unknown"


class TestSimilarityScore:
    def _make_candidate(self, category="cpu", severity="high", cpu=90.0, memory=30.0, disk=20.0,
                        tags=None, success=None) -> IncidentMemory:
        m = MagicMock(spec=IncidentMemory)
        m.category = category
        m.severity = severity
        m.metrics_snapshot = {"cpu": cpu, "memory": memory, "disk": disk}
        m.tags = tags or ["cpu", "high", "process"]
        m.success = success
        return m

    def test_perfect_match_scores_high(self):
        c = self._make_candidate(category="cpu", severity="high", cpu=92.0, success=True)
        score = _similarity_score(
            c, "cpu", "high", {"cpu": 92.0, "memory": 30.0, "disk": 20.0},
            ["cpu", "high", "process"]
        )
        assert score >= 0.70  # category(0.3) + metrics(0.3) + tags(0.25) + severity(0.1) + success(0.05)

    def test_category_mismatch_reduces_score(self):
        c = self._make_candidate(category="memory", severity="high", cpu=90.0)
        score = _similarity_score(
            c, "cpu", "high", {"cpu": 90.0, "memory": 30.0, "disk": 20.0}, ["cpu"]
        )
        assert score < 0.50  # no category bonus

    def test_successful_fix_adds_bonus(self):
        c_ok   = self._make_candidate(category="cpu", success=True)
        c_fail = self._make_candidate(category="cpu", success=False)
        s_ok   = _similarity_score(c_ok,   "cpu", "high", {"cpu": 90.0, "memory": 30.0, "disk": 20.0}, [])
        s_fail = _similarity_score(c_fail, "cpu", "high", {"cpu": 90.0, "memory": 30.0, "disk": 20.0}, [])
        assert s_ok > s_fail

    def test_score_bounded_0_to_1(self):
        c = self._make_candidate(success=True)
        s = _similarity_score(c, "cpu", "high", {"cpu": 92.0, "memory": 30.0, "disk": 20.0}, ["cpu"])
        assert 0.0 <= s <= 1.0


class TestBuildMemoryContext:
    def test_empty_list_returns_no_match_message(self):
        ctx = build_memory_context([])
        assert "no similar incidents" in ctx.lower()

    def test_formats_each_match(self):
        matches = [
            {
                "title": "CPU Spike Incident",
                "similarity_score": 0.85,
                "root_cause": "Runaway process",
                "recommended_action": "kill_process",
                "executed_action": "kill_process",
                "success": True,
                "resolution_time": 120.0,
                "metrics_snapshot": {"cpu": 92.0, "memory": 40.0, "disk": 30.0},
            }
        ]
        ctx = build_memory_context(matches)
        assert "CPU Spike Incident" in ctx
        assert "85%" in ctx
        assert "Runaway process" in ctx
        assert "kill_process" in ctx
        assert "Resolved" in ctx

    def test_shows_unknown_outcome_when_success_none(self):
        matches = [
            {
                "title": "Disk Full",
                "similarity_score": 0.50,
                "root_cause": "Log files",
                "recommended_action": "disk_cleanup",
                "executed_action": None,
                "success": None,
                "resolution_time": None,
                "metrics_snapshot": {},
            }
        ]
        ctx = build_memory_context(matches)
        assert "Unknown" in ctx or "unknown" in ctx


# ── Async integration tests (with mocked DB session) ─────────────────────────

@pytest.mark.asyncio
async def test_save_incident_memory_adds_row():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    from app.api.incident_memory import save_incident_memory
    entry = await save_incident_memory(
        db,
        org_id="org-1",
        title="High CPU",
        severity="high",
        category="cpu",
        metrics_snapshot={"cpu": 91.0, "memory": 40.0, "disk": 20.0},
        root_cause="Runaway process consuming CPU",
        reasoning="Step 1: CPU=91%. Step 2: top process=python",
        hypotheses=[{"cause": "Memory leak", "confidence": 0.7, "evidence": ["cpu=91%"]}],
        recommended_action="kill_process",
    )
    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    assert entry.org_id == "org-1"
    assert entry.category == "cpu"
    assert "cpu" in (entry.tags or [])


@pytest.mark.asyncio
async def test_find_similar_incidents_returns_empty_when_no_history():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    from app.api.incident_memory import find_similar_incidents
    results = await find_similar_incidents(
        db,
        org_id="org-1",
        category="cpu",
        severity="high",
        metrics={"cpu": 90.0, "memory": 30.0, "disk": 20.0},
    )
    assert results == []


@pytest.mark.asyncio
async def test_find_similar_incidents_scores_and_sorts():
    high_match = MagicMock(spec=IncidentMemory)
    high_match.category = "cpu"
    high_match.severity = "high"
    high_match.metrics_snapshot = {"cpu": 92.0, "memory": 30.0, "disk": 20.0}
    high_match.tags = ["cpu", "high", "process", "runaway"]
    high_match.success = True
    high_match.root_cause = "Runaway process"
    high_match.recommended_action = "kill_process"
    high_match.executed_action = "kill_process"
    high_match.resolution_time = 60.0
    high_match.title = "High CPU"
    high_match.id = "mem-001"
    high_match.created_at = MagicMock()
    high_match.created_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"

    low_match = MagicMock(spec=IncidentMemory)
    low_match.category = "disk"       # different category
    low_match.severity = "low"
    low_match.metrics_snapshot = {"cpu": 20.0, "memory": 20.0, "disk": 91.0}
    low_match.tags = ["disk", "low"]
    low_match.success = False
    low_match.root_cause = "Disk full"
    low_match.recommended_action = "disk_cleanup"
    low_match.executed_action = None
    low_match.resolution_time = None
    low_match.title = "Disk Full"
    low_match.id = "mem-002"
    low_match.created_at = MagicMock()
    low_match.created_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [high_match, low_match]
    db.execute = AsyncMock(return_value=mock_result)

    from app.api.incident_memory import find_similar_incidents
    results = await find_similar_incidents(
        db,
        org_id="org-1",
        category="cpu",
        severity="high",
        metrics={"cpu": 91.0, "memory": 30.0, "disk": 20.0},
        root_cause_hint="process consuming cpu",
    )

    assert len(results) >= 1
    # high_match should score higher than low_match
    scores = [r["similarity_score"] for r in results]
    if len(results) > 1:
        assert scores[0] >= scores[1]
    assert results[0]["title"] == "High CPU"
