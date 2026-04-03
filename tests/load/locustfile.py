"""
tests/load/locustfile.py — Locust load test scenarios for AIOps Bot.

Three HttpUser classes cover the three highest-stress surfaces:
    AuthLoadTest          — /auth/login (auth_api, port 5001 by default)
    MetricIngestionTest   — /ingest/heartbeat (core_api, port 8000 by default)
    DashboardLoadTest     — /api/orgs/{org_id}/metrics + /api/orgs/{org_id}/alerts (core_api)

Environment variables (all optional — defaults work against local dev stack):
    AUTH_API_HOST       Full base URL for auth_api   (default: http://localhost:5001)
    CORE_API_HOST       Full base URL for core_api   (default: http://localhost:8000)
    LOAD_TEST_EMAIL     Admin email                  (default: admin@company.local)
    LOAD_TEST_PASSWORD  Admin password               (default: Admin@1234)
    AGENT_KEY           Raw X-Agent-Key for heartbeat ingest
    ORG_ID              Organisation UUID for ingest + dashboard reads

Run headless examples:
    # Auth only, 50 users, 60 s
    locust -f tests/load/locustfile.py AuthLoadTest \\
        --headless -u 50 -r 5 -t 60s --host http://localhost:5001

    # All classes against core_api
    locust -f tests/load/locustfile.py \\
        --headless -u 100 -r 10 -t 60s --host http://localhost:8000

    # List available classes
    locust -f tests/load/locustfile.py --list
"""
from __future__ import annotations

import os
import random
from typing import Optional

from locust import HttpUser, between, task, events

# ── Configuration from environment ───────────────────────────────────────────

_AUTH_HOST  = os.getenv("AUTH_API_HOST",      "http://localhost:5001")
_CORE_HOST  = os.getenv("CORE_API_HOST",      "http://localhost:8000")
_EMAIL      = os.getenv("LOAD_TEST_EMAIL",    "admin@company.local")
_PASSWORD   = os.getenv("LOAD_TEST_PASSWORD", "Admin@1234")
_AGENT_KEY  = os.getenv("AGENT_KEY",          "")
_ORG_ID     = os.getenv("ORG_ID",             "")

# Thresholds (ms) — kept in sync with thresholds.json
_AUTH_P95_MAX       = 500
_INGEST_P95_MAX     = 200
_DASHBOARD_P95_MAX  = 300
_ERROR_RATE_MAX_PCT = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1 — Authentication
# Target: 50 concurrent users
# p95 < 500 ms
# ─────────────────────────────────────────────────────────────────────────────

class AuthLoadTest(HttpUser):
    """
    Simulates users logging in.
    90 % use valid credentials; 10 % use a wrong password so we also
    exercise the failure path and rate-limit response.
    The host is overridden to _AUTH_HOST because auth runs on a different
    port than core_api.
    """
    host       = _AUTH_HOST
    wait_time  = between(1, 3)

    @task(9)
    def login_valid(self) -> None:
        with self.client.post(
            "/auth/login",
            json={"email": _EMAIL, "password": _PASSWORD},
            catch_response=True,
            name="POST /auth/login (valid)",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                # Rate-limited — mark as success so the error rate metric
                # reflects real failures rather than intentional throttling.
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:120]}")

    @task(1)
    def login_invalid(self) -> None:
        with self.client.post(
            "/auth/login",
            json={"email": _EMAIL, "password": "wrong-password-intentional"},
            catch_response=True,
            name="POST /auth/login (invalid)",
        ) as resp:
            # 401 is the expected/correct response for bad credentials.
            if resp.status_code in (401, 422, 429):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2 — Metric Ingestion
# Simulates 10 agents each sending a heartbeat every 5 seconds.
# Target: 100 concurrent users   p95 < 200 ms
# ─────────────────────────────────────────────────────────────────────────────

def _random_metrics() -> dict:
    """Generate a realistic-looking metric payload."""
    return {
        "cpu":         round(random.uniform(5.0, 95.0), 2),
        "memory":      round(random.uniform(20.0, 90.0), 2),
        "disk":        round(random.uniform(10.0, 85.0), 2),
        "network_in":  random.randint(0, 10_000_000),
        "network_out": random.randint(0, 5_000_000),
        "temperature": round(random.uniform(35.0, 80.0), 1),
        "processes":   random.randint(50, 300),
        "uptime_secs": random.randint(3600, 2_592_000),
    }


class MetricIngestionTest(HttpUser):
    """
    Simulates agents POSTing heartbeats every ~5 seconds.
    Requires AGENT_KEY and ORG_ID environment variables to be set.
    If either is missing the scenario fails fast during startup.
    """
    host      = _CORE_HOST
    wait_time = between(4, 6)

    _warned = False

    def on_start(self) -> None:
        if not _AGENT_KEY or not _ORG_ID:
            raise RuntimeError(
                "AGENT_KEY and ORG_ID are required to run MetricIngestionTest. "
                "Set both environment variables before starting the load test."
            )

    @task
    def send_heartbeat(self) -> None:
        payload = {
            "org_id":  _ORG_ID,
            "metrics": _random_metrics(),
        }
        with self.client.post(
            "/ingest/heartbeat",
            json=payload,
            headers={"X-Agent-Key": _AGENT_KEY},
            catch_response=True,
            name="POST /ingest/heartbeat",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                resp.success()   # rate-limited is expected under load
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:120]}")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3 — Dashboard Reader
# Simulates users refreshing the dashboard every ~10 seconds.
# Target: 30 concurrent users   p95 < 300 ms
# ─────────────────────────────────────────────────────────────────────────────

class DashboardLoadTest(HttpUser):
    """
    Simulates a logged-in user repeatedly loading the dashboard.
    Obtains a JWT on start and uses it for all subsequent reads.
    Falls back gracefully when the auth step fails (e.g. server not running).
    """
    host      = _CORE_HOST
    wait_time = between(8, 12)

    _jwt: Optional[str] = None

    def on_start(self) -> None:
        """Login once to get a JWT; store it for subsequent requests."""
        if not _ORG_ID:
            raise RuntimeError(
                "ORG_ID is required to run DashboardLoadTest. Set the "
                "environment variable before starting the load test."
            )
        try:
            resp = self.client.post(
                f"{_AUTH_HOST}/auth/login",
                json={"email": _EMAIL, "password": _PASSWORD},
                name="on_start: login",
            )
            if resp.status_code == 200:
                data = resp.json()
                self._jwt = data.get("access_token") or data.get("token")
            if not self._jwt:
                raise RuntimeError(
                    "DashboardLoadTest could not acquire a JWT during startup. "
                    "Check AUTH_API_HOST and test credentials."
                )
        except Exception as exc:  # server not reachable during tests
            raise RuntimeError(f"DashboardLoadTest startup failed: {exc}") from exc

    def _auth_headers(self) -> dict:
        if self._jwt:
            return {"Authorization": f"Bearer {self._jwt}"}
        return {}

    def _org_path(self, suffix: str) -> str:
        if _ORG_ID:
            return f"/api/orgs/{_ORG_ID}{suffix}"
        # Fallback: use a placeholder that will return 404 but still exercises
        # the routing and auth middleware layers.
        return f"/api/orgs/load-test-org{suffix}"

    @task(3)
    def get_metrics(self) -> None:
        self.client.get(
            self._org_path("/metrics"),
            headers=self._auth_headers(),
            name="GET /api/orgs/{org}/metrics",
        )

    @task(2)
    def get_alerts(self) -> None:
        self.client.get(
            self._org_path("/alerts"),
            headers=self._auth_headers(),
            name="GET /api/orgs/{org}/alerts",
        )

    @task(1)
    def get_health(self) -> None:
        with self.client.get(
            "/health",
            catch_response=True,
            name="GET /health",
        ) as resp:
            if resp.status_code in (200, 503):
                resp.success()   # 503 means DB is down — still a valid response
            else:
                resp.failure(f"Unexpected {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# Threshold enforcement via Locust events
# Prints a PASS/FAIL summary when a headless run finishes.
# ─────────────────────────────────────────────────────────────────────────────

@events.quitting.add_listener
def _check_thresholds(environment, **_kwargs) -> None:
    """
    Called when Locust is about to exit.  Checks p95 response times and
    overall error rate against thresholds.json values.  Sets exit_code=1
    if any threshold is breached so CI pipelines detect failures.
    """
    stats = environment.stats

    # Gather per-endpoint p95 and error rate
    failures: list[str] = []

    for entry in stats.entries.values():
        name = entry.name
        p95  = entry.get_response_time_percentile(0.95)
        if p95 is None:
            continue

        if "login" in name.lower() and p95 > _AUTH_P95_MAX:
            failures.append(
                f"  FAIL  {name}: p95={p95:.0f}ms > threshold {_AUTH_P95_MAX}ms"
            )
        elif "heartbeat" in name.lower() and p95 > _INGEST_P95_MAX:
            failures.append(
                f"  FAIL  {name}: p95={p95:.0f}ms > threshold {_INGEST_P95_MAX}ms"
            )
        elif ("/metrics" in name.lower() or "/alerts" in name.lower() or "/health" in name.lower()) \
                and p95 > _DASHBOARD_P95_MAX:
            failures.append(
                f"  FAIL  {name}: p95={p95:.0f}ms > threshold {_DASHBOARD_P95_MAX}ms"
            )

    # Global error rate
    total_reqs  = stats.total.num_requests
    total_fails = stats.total.num_failures
    if total_reqs == 0:
        failures.append(
            "  FAIL  No requests were recorded; a scenario likely failed during startup or was misconfigured"
        )
    else:
        error_pct = (total_fails / total_reqs) * 100
        if error_pct > _ERROR_RATE_MAX_PCT:
            failures.append(
                f"  FAIL  Error rate: {error_pct:.2f}% > threshold {_ERROR_RATE_MAX_PCT}%"
            )

    border = "=" * 60
    if failures:
        print(f"\n{border}")
        print("LOAD TEST RESULT: FAIL")
        print(border)
        for msg in failures:
            print(msg)
        print(border)
        environment.process_exit_code = 1
    else:
        print(f"\n{border}")
        print("LOAD TEST RESULT: PASS — all thresholds met")
        print(border)
