"""
tests/test_metrics.py — Unit tests for the /ingest/heartbeat and
/api/orgs/{org_id}/metrics endpoints in core_api.
"""
from __future__ import annotations

import uuid

import pytest
from database import Agent, Organization
from helpers import admin_jwt as _admin_token
from httpx import AsyncClient

# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

async def test_metric_stored_correctly(
    core_client: AsyncClient,
    sample_org: Organization,
    sample_agent: tuple[Agent, str],
):
    """Values POSTed via heartbeat are faithfully persisted and returned."""
    agent, raw_key = sample_agent
    resp = await core_client.post(
        "/ingest/heartbeat",
        headers={"X-Agent-Key": raw_key},
        json={
            "org_id": sample_org.id,
            "metrics": {
                "cpu": 55.0,
                "memory": 70.0,
                "disk": 30.0,
                "network_in": 2048,
                "network_out": 1024,
            },
        },
    )
    assert resp.status_code == 200

    token = _admin_token(sample_org.id)
    list_resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    snapshots = list_resp.json()
    assert snapshots, "Expected at least one metric snapshot"

    snap = snapshots[0]
    assert snap["cpu"] == 55.0
    assert snap["memory"] == 70.0
    assert snap["disk"] == 30.0
    assert snap["network_in"] == 2048
    assert snap["network_out"] == 1024
    assert snap["org_id"] == sample_org.id
    assert snap["agent_id"] == agent.id


async def test_metric_retrieval_returns_correct_format(
    core_client: AsyncClient,
    sample_org: Organization,
    sample_metric: dict,
):
    """GET /metrics response contains all required fields with correct types."""
    token = _admin_token(sample_org.id)
    resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    snapshots = resp.json()
    assert isinstance(snapshots, list)
    assert len(snapshots) >= 1

    snap = snapshots[0]
    required_fields = {"id", "org_id", "agent_id", "timestamp", "cpu", "memory", "disk"}
    assert required_fields.issubset(snap.keys()), (
        f"Missing fields: {required_fields - snap.keys()}"
    )
    assert isinstance(snap["cpu"], (int, float))
    assert isinstance(snap["memory"], (int, float))
    assert isinstance(snap["disk"], (int, float))
    assert isinstance(snap["timestamp"], str)


async def test_metric_with_missing_fields_is_rejected(
    core_client: AsyncClient,
    sample_org: Organization,
    sample_agent: tuple[Agent, str],
):
    """Heartbeat without required metric fields returns 422 Unprocessable Entity."""
    _, raw_key = sample_agent
    resp = await core_client.post(
        "/ingest/heartbeat",
        headers={"X-Agent-Key": raw_key},
        json={
            "org_id": sample_org.id,
            "metrics": {
                # cpu is required but omitted
                "memory": 50.0,
                "disk": 40.0,
            },
        },
    )
    assert resp.status_code == 422


async def test_metric_timestamp_is_set_automatically(
    core_client: AsyncClient,
    sample_org: Organization,
    sample_agent: tuple[Agent, str],
):
    """Server sets the timestamp on ingest; client must not supply it."""
    agent, raw_key = sample_agent
    resp = await core_client.post(
        "/ingest/heartbeat",
        headers={"X-Agent-Key": raw_key},
        json={
            "org_id": sample_org.id,
            "metrics": {"cpu": 10.0, "memory": 20.0, "disk": 30.0},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # The response contains received_at set by the server
    assert "received_at" in data
    ts = data["received_at"]
    assert ts, "received_at should be a non-empty ISO timestamp"
    # Verify the stored snapshot also has a timestamp
    token = _admin_token(sample_org.id)
    list_resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    snaps = list_resp.json()
    assert snaps[0]["timestamp"] is not None


async def test_metric_query_returns_latest_first(
    core_client: AsyncClient,
    sample_org: Organization,
    sample_agent: tuple[Agent, str],
):
    """Metrics list is ordered newest-first (descending timestamp)."""
    _, raw_key = sample_agent
    # Send two heartbeats sequentially
    for cpu_val in [11.0, 22.0]:
        r = await core_client.post(
            "/ingest/heartbeat",
            headers={"X-Agent-Key": raw_key},
            json={
                "org_id": sample_org.id,
                "metrics": {"cpu": cpu_val, "memory": 50.0, "disk": 50.0},
            },
        )
        assert r.status_code == 200

    token = _admin_token(sample_org.id)
    resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    snaps = resp.json()
    assert len(snaps) >= 2
    timestamps = [s["timestamp"] for s in snaps]
    # Each timestamp should be >= the next one (descending order)
    for i in range(len(timestamps) - 1):
        assert timestamps[i] >= timestamps[i + 1], (
            f"Not sorted newest-first at index {i}: {timestamps[i]} < {timestamps[i+1]}"
        )
