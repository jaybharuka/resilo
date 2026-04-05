# Phase 3 Load and Tracing Execution

## Load Testing (Issue #27)

Use the existing Locust suite to simulate 100 concurrent agents:

```bash
bash tests/load/run_load_tests.sh
```

Scenario coverage:
- `AuthLoadTest` (50 users)
- `MetricIngestionTest` (100 users)
- `DashboardLoadTest` (30 users)

Thresholds and failure gates are enforced in:
- `tests/load/locustfile.py`
- `tests/load/thresholds.json`

Capture in report:
- Throughput (req/s)
- Latency (p95)
- Failure rate (%)
- Primary bottlenecks

## Distributed Tracing (Issue #28)

Tracing baseline exists in:
- `app/core/trace_context.py`
- `app/core/http_client.py`
- `config/otel.py`

Validation checklist:
1. Verify incoming requests include `traceparent`.
2. Verify outbound calls propagate trace headers.
3. Confirm logs include trace IDs for correlation.
4. Confirm traces export to configured backend.
