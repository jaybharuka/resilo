#!/usr/bin/env bash
# tests/load/run_load_tests.sh
#
# Runs all three Locust load test scenarios sequentially, saves CSV results,
# and exits with code 1 if any scenario breaches thresholds.
#
# Usage:
#   bash tests/load/run_load_tests.sh               # run all scenarios
#   bash tests/load/run_load_tests.sh --dry-run     # show what would run
#
# Environment variables (all optional):
#   AUTH_API_HOST       default: http://localhost:5001
#   CORE_API_HOST       default: http://localhost:8000
#   LOAD_TEST_EMAIL     default: admin@company.local
#   LOAD_TEST_PASSWORD  default: Admin@1234
#   AGENT_KEY           agent X-Agent-Key (required for MetricIngestionTest)
#   ORG_ID              organisation UUID  (required for MetricIngestionTest + DashboardLoadTest)
#   DURATION            seconds each scenario runs   default: 60
#   RESULTS_DIR         output folder                default: tests/load/results

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
AUTH_API_HOST="${AUTH_API_HOST:-http://localhost:5001}"
CORE_API_HOST="${CORE_API_HOST:-http://localhost:8000}"
DURATION="${DURATION:-60}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${SCRIPT_DIR}/results}"
LOCUSTFILE="${SCRIPT_DIR}/locustfile.py"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
_section() { echo; echo "════════════════════════════════════════════════════════════"; echo "  $*"; echo "════════════════════════════════════════════════════════════"; }
_pass()    { echo "  ✔  PASS: $*"; }
_fail()    { echo "  ✘  FAIL: $*"; }

_run_scenario() {
  local class="$1"
  local host="$2"
  local users="$3"
  local spawn_rate="$4"
  local prefix="${RESULTS_DIR}/${class}"

  local cmd=(
    locust
      -f "${LOCUSTFILE}"
      "${class}"
      --headless
      --host "${host}"
      -u "${users}"
      -r "${spawn_rate}"
      -t "${DURATION}s"
      --csv "${prefix}"
      --csv-full-history
      --only-summary
  )

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "  [dry-run] Would run: ${cmd[*]}"
    return 0
  fi

  mkdir -p "${RESULTS_DIR}"
  echo "  Running: ${cmd[*]}"
  "${cmd[@]}"
  return $?
}

# ── Main ──────────────────────────────────────────────────────────────────────
_section "AIOps Bot — Load Test Suite"
echo "  Auth API host : ${AUTH_API_HOST}"
echo "  Core API host : ${CORE_API_HOST}"
echo "  Duration      : ${DURATION}s per scenario"
echo "  Results dir   : ${RESULTS_DIR}"
[[ "${DRY_RUN}" == "true" ]] && echo "  Mode          : DRY RUN (no actual requests)"

OVERALL_EXIT=0

# ── Scenario 1: Auth ──────────────────────────────────────────────────────────
_section "Scenario 1/3 — AuthLoadTest (50 users, p95 < 500 ms)"
if _run_scenario "AuthLoadTest" "${AUTH_API_HOST}" 50 5; then
  _pass "AuthLoadTest completed"
else
  _fail "AuthLoadTest exited non-zero (threshold breach or error)"
  OVERALL_EXIT=1
fi

# ── Scenario 2: Metric Ingestion ──────────────────────────────────────────────
if [[ -z "${AGENT_KEY:-}" || -z "${ORG_ID:-}" ]]; then
  _fail "AGENT_KEY and ORG_ID must be set before running MetricIngestionTest"
  OVERALL_EXIT=1
else
_section "Scenario 2/3 — MetricIngestionTest (100 users, p95 < 200 ms)"
if _run_scenario "MetricIngestionTest" "${CORE_API_HOST}" 100 10; then
  _pass "MetricIngestionTest completed"
else
  _fail "MetricIngestionTest exited non-zero (threshold breach or error)"
  OVERALL_EXIT=1
fi
fi

# ── Scenario 3: Dashboard ─────────────────────────────────────────────────────
if [[ -z "${ORG_ID:-}" ]]; then
  _fail "ORG_ID must be set before running DashboardLoadTest"
  OVERALL_EXIT=1
else
_section "Scenario 3/3 — DashboardLoadTest (30 users, p95 < 300 ms)"
if _run_scenario "DashboardLoadTest" "${CORE_API_HOST}" 30 3; then
  _pass "DashboardLoadTest completed"
else
  _fail "DashboardLoadTest exited non-zero (threshold breach or error)"
  OVERALL_EXIT=1
fi
fi

# ── Final summary ─────────────────────────────────────────────────────────────
_section "Load Test Suite — Final Result"
if [[ "${OVERALL_EXIT}" -eq 0 ]]; then
  echo "  PASS — all scenarios met thresholds"
else
  echo "  FAIL — one or more scenarios breached thresholds"
  echo "  Check CSV reports in: ${RESULTS_DIR}"
fi

exit "${OVERALL_EXIT}"
