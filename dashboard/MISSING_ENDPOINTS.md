# Backend Endpoints — Implementation Status

> All endpoints below are now implemented in `app/api/v1_api.py`.
> Registered in `main.py` and `app/api/core_api.py` under the `/api/v1` prefix.

---

# Originally Missing Backend Endpoints

These endpoints are called by the dashboard but do not yet exist in the FastAPI backend.
Each section lists the route, expected request/response shape, and which component consumes it.

---

## Feature 1 — Live Remediation Actions Feed

**Component:** `RemediationFeed.js` (falls back to `/api/remediation/history` if missing)

### `GET /api/v1/remediation/actions`

| Param | Type | Description |
|---|---|---|
| `limit` | int (query) | Max number of entries, default 20 |

**Response** `200 application/json`
```json
{
  "items": [
    {
      "id": "uuid",
      "executed_at": "2025-01-01T12:00:00Z",
      "component": "api-gateway",
      "action": "scale_up",
      "trigger_metric": "cpu_usage",
      "trigger_value": 92.4,
      "outcome": "success",
      "details": {}
    }
  ],
  "total": 100
}
```

**Error states expected by UI:**
- `502` → "Backend unavailable"
- Empty `items` array → "No actions yet"

---

## Feature 2 — Tenant Health Heatmap

**Component:** `TenantHealthHeatmap.js`

### `GET /api/v1/tenants/health-summary`

No query params.

**Response** `200 application/json`
```json
{
  "tenants": [
    {
      "org_id": "uuid",
      "org_name": "Acme Corp",
      "health_score": 87,
      "top_issue": "High memory on agent-02",
      "last_incident_at": "2025-01-01T10:00:00Z",
      "error_rate": 0.4,
      "p95_latency_ms": 210,
      "active_sessions": 14,
      "failed_auth_1h": 0
    }
  ]
}
```

**Auth:** Requires `admin` role (org admins see only their own org).

**Error states expected by UI:**
- `404` / `501` → "ENDPOINT PENDING" message with endpoint path
- Empty `tenants` → "No tenants found"

---

## Feature 3 — Predictive Alert Timeline

**Component:** `PredictiveTimeline.js`

### `GET /api/v1/predictions/upcoming`

No query params (returns next 2 hours by default).

**Response** `200 application/json`
```json
{
  "predictions": [
    {
      "name": "CPU saturation",
      "severity": "warning",
      "predicted_at": "2025-01-01T13:30:00Z",
      "confidence": 0.82,
      "reason": "CPU trend at 78% and climbing. Historical pattern indicates saturation within 90 minutes.",
      "contributing_signals": [
        "cpu_usage trending +3%/min",
        "memory at 71%",
        "3 heavy batch jobs scheduled at 13:00"
      ]
    }
  ]
}
```

**Backed by:** `AdaptiveMLPlatform` — the platform already ingests metrics; it needs a `/predictions/upcoming` read endpoint.

**Error states:** `404`/`501` → "ENDPOINT PENDING"; empty → "No alerts predicted in next 2H"

---

## Feature 4 — Circuit Breaker Status

**Component:** `CircuitBreakerPanel.js`

### `GET /api/v1/remediation/circuit-breaker/status`

No params.

**Response** `200 application/json`
```json
{
  "breakers": [
    {
      "component": "payment-service",
      "service": "billing",
      "state": "OPEN",
      "failure_count": 8,
      "threshold": 5,
      "opened_at": "2025-01-01T11:55:00Z",
      "timeout_ms": 30000,
      "last_success_at": "2025-01-01T11:54:20Z"
    }
  ]
}
```

States: `CLOSED` | `OPEN` | `HALF_OPEN`

### `POST /api/v1/remediation/circuit-breaker/{component}/reset`

Path param: `component` — string name of the component to reset.

**Response** `200`
```json
{ "component": "payment-service", "state": "CLOSED", "reset_at": "2025-01-01T12:05:00Z" }
```

**Error states:** `404`/`501` → "ENDPOINT PENDING"; empty breakers → "No circuit breakers configured"

---

## Feature 5 — API Key Usage Heatmap

**Component:** `ApiKeyHeatmap.js`

### `GET /api/v1/api-keys/usage-heatmap`

| Param | Type | Description |
|---|---|---|
| `hours` | int (query) | Look-back window, default 24 |

**Response** `200 application/json`
```json
{
  "keys": [
    {
      "key_id": "uuid",
      "key_label": "Mobile App v2",
      "data": {
        "0":  { "requests": 120, "errors": 1,  "error_rate": 0.83, "p95_ms": 145 },
        "1":  { "requests": 80,  "errors": 0,  "error_rate": 0,    "p95_ms": 110 },
        "13": { "requests": 450, "errors": 28, "error_rate": 6.22, "p95_ms": 890 }
      }
    }
  ]
}
```

`data` keys are hour integers 0–23 (UTC). Missing hours = no traffic.

**Error states:** `404`/`501` → "ENDPOINT PENDING"; empty `keys` → "No API key data"

---

## Feature 6 — Incident Declare / Resolve

**Component:** `IncidentDeclare.js` (button in Topbar)

### `POST /api/v1/incidents`

**Request body**
```json
{
  "severity": "SEV2",
  "service": "API Gateway",
  "description": "Elevated error rate on /checkout — 503 spike at 13:42 UTC",
  "commander": "Jane Smith"
}
```

**Response** `201`
```json
{
  "id": "INC-2025-001",
  "severity": "SEV2",
  "service": "API Gateway",
  "description": "...",
  "commander": "Jane Smith",
  "declared_at": "2025-01-01T13:42:00Z",
  "status": "active"
}
```

### `GET /api/v1/incidents/active`

Returns the currently active (unresolved) incident or `null`.

**Response** `200`
```json
{
  "id": "INC-2025-001",
  "severity": "SEV2",
  "service": "API Gateway",
  "status": "active",
  "declared_at": "2025-01-01T13:42:00Z"
}
```

Returns `404` or `{ "id": null }` when no active incident exists.

### `POST /api/v1/incidents/{id}/resolve`

**Response** `200`
```json
{ "id": "INC-2025-001", "status": "resolved", "resolved_at": "2025-01-01T14:10:00Z" }
```

---

## Notes for Backend Team

- All endpoints require `Authorization: Bearer <token>` (JWT from `/auth/login`).
- Org-scope: non-admin users see only their own org's data.
- Errors should follow the existing shape: `{ "detail": "human-readable message" }`.
- `404` or `501` responses from missing endpoints are handled gracefully by the UI with an "ENDPOINT PENDING" state — no placeholder data is shown.
