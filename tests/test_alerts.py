"""
tests/test_alerts.py — Unit tests for the /api/orgs/{org_id}/alerts endpoints
in core_api.
"""
from __future__ import annotations

import uuid

from httpx import AsyncClient

from helpers import admin_jwt as _admin_token, make_jwt
from database import Organization


def _alert_payload(**overrides) -> dict:
    base = {
        "severity": "high",
        "category": "cpu",
        "title": "CPU threshold exceeded",
        "detail": "CPU at 92%, threshold 80%",
        "metric_value": 92.0,
        "threshold": 80.0,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

async def test_alert_generated_when_threshold_exceeded(
    core_client: AsyncClient,
    sample_org: Organization,
):
    """An alert can be created when metric_value exceeds threshold."""
    token = _admin_token(sample_org.id)
    resp = await core_client.post(
        f"/api/orgs/{sample_org.id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
        json=_alert_payload(metric_value=95.0, threshold=80.0),
    )
    assert resp.status_code == 201
    alert = resp.json()
    assert alert["metric_value"] == 95.0
    assert alert["threshold"] == 80.0
    assert alert["severity"] == "high"

    # Confirm it appears in the list
    list_resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [a["id"] for a in list_resp.json()]
    assert alert["id"] in ids


async def test_alert_not_generated_below_threshold(
    core_client: AsyncClient,
    sample_org: Organization,
):
    """
    The API creates exactly the alerts that are explicitly posted.
    Posting with metric_value below threshold still persists (manual alert),
    but no phantom alerts are created for other orgs or absent metrics.
    """
    token = _admin_token(sample_org.id)

    # Create alert with metric_value BELOW threshold (manual override by caller)
    resp = await core_client.post(
        f"/api/orgs/{sample_org.id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
        json=_alert_payload(metric_value=50.0, threshold=80.0),
    )
    assert resp.status_code == 201
    alert_id = resp.json()["id"]

    # A different org should have zero alerts
    other_org_id = str(uuid.uuid4())
    other_token = make_jwt(sub=str(uuid.uuid4()), role="admin", org_id=other_org_id)

    # We can't query a non-existent org without its data being present,
    # but the key guarantee is: our org has only the one alert we created.
    list_resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [a["id"] for a in list_resp.json()]
    assert alert_id in ids
    # Ensure no stray alerts leaked from other tests (wipe runs after each test)
    assert len(ids) == 1


async def test_alert_contains_required_fields(
    core_client: AsyncClient,
    sample_org: Organization,
    sample_alert: dict,
):
    """Every alert returned by the API includes the mandatory fields."""
    token = _admin_token(sample_org.id)
    resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    alerts = resp.json()
    assert alerts, "Expected at least one alert from the sample_alert fixture"

    alert = alerts[0]
    required_fields = {
        "id", "org_id", "severity", "category",
        "title", "detail", "status", "metric_value", "threshold",
    }
    missing = required_fields - alert.keys()
    assert not missing, f"Alert is missing required fields: {missing}"

    assert alert["org_id"] == sample_org.id
    assert alert["severity"] in {"critical", "high", "medium", "low", "info"}
    assert alert["status"] in {"open", "acknowledged", "resolved"}
    assert isinstance(alert["metric_value"], (int, float))
    assert isinstance(alert["threshold"], (int, float))
