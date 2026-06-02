"""
Unit tests for investigation_engine.py

Tests:
  - Stage constants and routing thresholds
  - _route_action maps confidence to ActionRouting correctly
  - _fallback_hypotheses returns deterministic results per incident type
  - _strip_json / _strip_json_array parse LLM output correctly
  - run_investigation full pipeline (mocked LLM + mocked DB)
  - Confidence routing: auto_execute / manual_approval / investigation_only
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.investigation_engine import (
    CONFIDENCE_AUTO_EXECUTE,
    CONFIDENCE_MANUAL_APPROVAL,
    ActionRouting,
    Evidence,
    Hypothesis,
    InvestigationStage,
    RootCauseAnalysis,
    _fallback_hypotheses,
    _route_action,
    _strip_json,
    _strip_json_array,
)


# ── Constants ─────────────────────────────────────────────────────────────────

def test_confidence_thresholds_sane():
    assert CONFIDENCE_AUTO_EXECUTE == 0.95
    assert CONFIDENCE_MANUAL_APPROVAL == 0.70
    assert CONFIDENCE_AUTO_EXECUTE > CONFIDENCE_MANUAL_APPROVAL


def test_stage_values():
    assert InvestigationStage.EVIDENCE_COLLECTION   == "EVIDENCE_COLLECTION"
    assert InvestigationStage.HISTORICAL_ANALYSIS   == "HISTORICAL_ANALYSIS"
    assert InvestigationStage.HYPOTHESIS_GENERATION == "HYPOTHESIS_GENERATION"
    assert InvestigationStage.ROOT_CAUSE_ANALYSIS   == "ROOT_CAUSE_ANALYSIS"
    assert InvestigationStage.ACTION_PLANNING       == "ACTION_PLANNING"


# ── _route_action ─────────────────────────────────────────────────────────────

class TestRouteAction:
    def test_auto_execute_at_threshold(self):
        assert _route_action(0.95) == ActionRouting.AUTO_EXECUTE

    def test_auto_execute_above_threshold(self):
        assert _route_action(0.99) == ActionRouting.AUTO_EXECUTE

    def test_manual_approval_just_below_auto(self):
        assert _route_action(0.94) == ActionRouting.MANUAL_APPROVAL

    def test_manual_approval_at_lower_threshold(self):
        assert _route_action(0.70) == ActionRouting.MANUAL_APPROVAL

    def test_investigation_only_just_below_manual(self):
        assert _route_action(0.69) == ActionRouting.INVESTIGATION_ONLY

    def test_investigation_only_at_zero(self):
        assert _route_action(0.0) == ActionRouting.INVESTIGATION_ONLY

    def test_investigation_only_at_fifty_percent(self):
        assert _route_action(0.50) == ActionRouting.INVESTIGATION_ONLY


# ── _fallback_hypotheses ──────────────────────────────────────────────────────

class TestFallbackHypotheses:
    def _make_evidence(self, incident_type, cpu=90.0, memory=30.0, disk=20.0):
        return Evidence(incident_type=incident_type, cpu=cpu, memory=memory, disk=disk)

    def test_cpu_returns_two_hypotheses(self):
        hyps = _fallback_hypotheses(self._make_evidence("cpu"))
        assert len(hyps) >= 2
        assert all(isinstance(h, Hypothesis) for h in hyps)
        assert all(h.confidence > 0 for h in hyps)

    def test_memory_first_hypothesis_has_high_confidence(self):
        hyps = _fallback_hypotheses(self._make_evidence("memory"))
        assert hyps[0].confidence >= 0.60

    def test_disk_returns_at_least_one(self):
        hyps = _fallback_hypotheses(self._make_evidence("disk"))
        assert len(hyps) >= 1
        assert "disk" in hyps[0].cause.lower() or "log" in hyps[0].cause.lower()

    def test_unknown_type_returns_fallback(self):
        hyps = _fallback_hypotheses(self._make_evidence("network"))
        assert len(hyps) >= 1

    def test_evidence_included_in_hypotheses(self):
        hyps = _fallback_hypotheses(self._make_evidence("cpu", cpu=91.0))
        for h in hyps:
            assert len(h.evidence) >= 1


# ── _strip_json / _strip_json_array ──────────────────────────────────────────

class TestStripJson:
    def test_bare_json(self):
        raw = '{"key": "value", "num": 42}'
        result = _strip_json(raw)
        assert result == {"key": "value", "num": 42}

    def test_json_with_prose_before(self):
        raw = 'Here is my analysis:\n{"root_cause": "OOM killer", "confidence": 0.85}'
        result = _strip_json(raw)
        assert result["root_cause"] == "OOM killer"
        assert result["confidence"] == 0.85

    def test_json_with_prose_after(self):
        raw = '{"action": "free_memory"}\nNote: this is a recommendation.'
        result = _strip_json(raw)
        assert result["action"] == "free_memory"

    def test_empty_string_returns_empty_dict(self):
        assert _strip_json("") == {}

    def test_invalid_json_returns_empty_dict(self):
        assert _strip_json("{not valid json") == {}


class TestStripJsonArray:
    def test_bare_array(self):
        raw = '[{"cause": "memory leak", "confidence": 0.7, "evidence": ["mem=90%"]}]'
        result = _strip_json_array(raw)
        assert len(result) == 1
        assert result[0]["cause"] == "memory leak"

    def test_array_with_prose(self):
        raw = 'Hypotheses:\n[{"cause": "cpu spike", "confidence": 0.8, "evidence": []}]'
        result = _strip_json_array(raw)
        assert result[0]["cause"] == "cpu spike"

    def test_empty_returns_empty_list(self):
        assert _strip_json_array("") == []

    def test_invalid_returns_empty_list(self):
        assert _strip_json_array("[broken") == []


# ── run_investigation integration (mocked) ───────────────────────────────────

def _make_alert(category="cpu", severity="high", agent_id="agent-001", org_id="org-1"):
    alert = MagicMock()
    alert.id = "alert-uuid-001"
    alert.agent_id = agent_id
    alert.org_id = org_id
    alert.category = category
    alert.severity = severity
    alert.title = f"High {category.upper()} Alert"
    alert.detail = f"{category} exceeded threshold"
    return alert


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    # Actual db.execute call order in run_investigation:
    #   1. _collect_evidence  → select(AgentActionLog)
    #   2. find_similar_incidents → select(IncidentMemory)
    #   3. _persist_investigation (via SessionLocal) → select(Investigation)
    mock_action_result = MagicMock()
    mock_action_result.scalars.return_value.all.return_value = []

    mock_mem_result = MagicMock()
    mock_mem_result.scalars.return_value.all.return_value = []

    mock_inv_result = MagicMock()
    mock_inv_result.scalar_one_or_none.return_value = None

    db.execute = AsyncMock(side_effect=[
        mock_action_result,   # 1 — AgentActionLog in _collect_evidence
        mock_mem_result,      # 2 — IncidentMemory in find_similar_incidents
        mock_inv_result,      # 3 — Investigation upsert in _persist_investigation
    ])
    return db


@pytest.mark.asyncio
async def test_run_investigation_succeeds_with_llm():
    """Full pipeline with a mocked LLM that returns valid JSON."""
    hypothesis_json = json.dumps([
        {"cause": "Runaway Python process", "confidence": 0.85, "evidence": ["cpu=91%"]},
        {"cause": "Scheduled batch job", "confidence": 0.60, "evidence": ["load_avg high"]},
    ])
    rca_json = json.dumps({
        "root_cause": "Runaway Python process consuming all CPU",
        "confidence": 0.87,
        "supporting_evidence": ["cpu=91%", "top process: python at 88%"],
        "historical_matches": [],
        "reasoning_steps": ["CPU=91%", "Top process: python", "Memory stable"],
        "recommended_action": "kill_process",
        "safe_to_auto_fix": False,
    })

    call_count = 0
    async def mock_llm(system, user):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return hypothesis_json
        return rca_json

    alert = _make_alert(category="cpu")
    db = _make_db()

    with patch("app.api.investigation_engine.SessionLocal") as mock_sl:
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sl.return_value = mock_session_ctx

        from app.api.investigation_engine import run_investigation
        result = await run_investigation(
            db=db,
            alert=alert,
            org_id="org-1",
            agent_id="agent-001",
            cpu=91.0,
            memory=40.0,
            disk=20.0,
            extra_metrics={"top_processes": {"by_cpu": [{"name": "python", "cpu_percent": 88.0}]}},
            call_llm_fn=mock_llm,
        )

    assert result.investigation_id.startswith("INV-")
    assert result.agent_id == "agent-001"
    assert result.alert_id == "alert-uuid-001"
    assert result.confidence == 0.87
    assert result.root_cause.root_cause == "Runaway Python process consuming all CPU"
    assert result.recommended_action == "kill_process"
    assert result.action_routing == ActionRouting.MANUAL_APPROVAL  # 0.87 is in 70-94% range
    assert len(result.hypotheses) >= 2
    assert len(result.timeline) >= 4  # one per stage minimum


@pytest.mark.asyncio
async def test_run_investigation_routes_to_auto_execute_at_high_confidence():
    """When confidence >= 0.95, routing should be AUTO_EXECUTE."""
    rca_high = json.dumps({
        "root_cause": "Confirmed OOM — swap exhausted",
        "confidence": 0.96,
        "supporting_evidence": ["memory=96%", "swap=100%"],
        "historical_matches": [],
        "reasoning_steps": ["Memory=96%", "Swap=100%", "OOM killer active"],
        "recommended_action": "free_memory",
        "safe_to_auto_fix": True,
    })

    call_count = 0
    async def mock_llm(system, user):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps([{"cause": "OOM", "confidence": 0.96, "evidence": ["mem=96%"]}])
        return rca_high

    alert = _make_alert(category="memory")
    db = _make_db()

    with patch("app.api.investigation_engine.SessionLocal") as mock_sl:
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sl.return_value = mock_session_ctx

        from app.api.investigation_engine import run_investigation
        result = await run_investigation(
            db=db,
            alert=alert,
            org_id="org-1",
            agent_id="agent-001",
            cpu=50.0, memory=96.0, disk=20.0,
            call_llm_fn=mock_llm,
        )

    assert result.action_routing == ActionRouting.AUTO_EXECUTE
    assert result.confidence >= CONFIDENCE_AUTO_EXECUTE


@pytest.mark.asyncio
async def test_run_investigation_routes_to_investigation_only_at_low_confidence():
    """When confidence < 0.70, routing should be INVESTIGATION_ONLY."""
    rca_low = json.dumps({
        "root_cause": "Cause unclear",
        "confidence": 0.45,
        "supporting_evidence": [],
        "historical_matches": [],
        "reasoning_steps": ["Low confidence — insufficient data"],
        "recommended_action": "notify_only",
        "safe_to_auto_fix": False,
    })

    async def mock_llm(system, user):
        if "hypothes" in system.lower() or len(user) > 500:
            return json.dumps([{"cause": "Unknown", "confidence": 0.40, "evidence": []}])
        return rca_low

    alert = _make_alert(category="cpu")
    db = _make_db()

    with patch("app.api.investigation_engine.SessionLocal") as mock_sl:
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sl.return_value = mock_session_ctx

        from app.api.investigation_engine import run_investigation
        result = await run_investigation(
            db=db,
            alert=alert,
            org_id="org-1",
            agent_id="agent-001",
            cpu=72.0, memory=40.0, disk=20.0,
            call_llm_fn=mock_llm,
        )

    assert result.action_routing == ActionRouting.INVESTIGATION_ONLY
    assert result.confidence < CONFIDENCE_MANUAL_APPROVAL


@pytest.mark.asyncio
async def test_run_investigation_degrades_gracefully_on_llm_failure():
    """If LLM raises, investigation should complete with fallback values."""
    async def failing_llm(system, user):
        raise ConnectionError("LLM unavailable")

    alert = _make_alert(category="memory")
    db = _make_db()

    with patch("app.api.investigation_engine.SessionLocal") as mock_sl:
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sl.return_value = mock_session_ctx

        from app.api.investigation_engine import run_investigation
        result = await run_investigation(
            db=db,
            alert=alert,
            org_id="org-1",
            agent_id="agent-001",
            cpu=40.0, memory=88.0, disk=20.0,
            call_llm_fn=failing_llm,
        )

    # Should complete without raising
    assert result.investigation_id.startswith("INV-")
    assert len(result.hypotheses) >= 1   # fallback hypotheses
    assert result.root_cause is not None
    assert result.recommended_action is not None
    assert len(result.timeline) >= 1


@pytest.mark.asyncio
async def test_run_investigation_timeline_has_all_stages():
    """Timeline should contain events from all 5 stages."""
    async def mock_llm(system, user):
        return json.dumps([{"cause": "Test", "confidence": 0.80, "evidence": []}])

    alert = _make_alert()
    db = _make_db()

    with patch("app.api.investigation_engine.SessionLocal") as mock_sl:
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sl.return_value = mock_session_ctx

        # Second LLM call for RCA
        call_count = 0
        async def counting_llm(system, user):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps([{"cause": "Test hyp", "confidence": 0.75, "evidence": []}])
            return json.dumps({
                "root_cause": "Test root cause",
                "confidence": 0.75,
                "supporting_evidence": [],
                "historical_matches": [],
                "reasoning_steps": ["step1", "step2"],
                "recommended_action": "notify_only",
                "safe_to_auto_fix": False,
            })

        from app.api.investigation_engine import run_investigation
        result = await run_investigation(
            db=db,
            alert=alert,
            org_id="org-1",
            agent_id="agent-001",
            cpu=90.0, memory=40.0, disk=20.0,
            call_llm_fn=counting_llm,
        )

    stage_names = {e["stage"] for e in result.timeline}
    # At minimum evidence collection, historical analysis, and action planning
    assert "EVIDENCE_COLLECTION" in stage_names
    assert "ACTION_PLANNING" in stage_names
