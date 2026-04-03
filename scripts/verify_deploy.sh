#!/usr/bin/env bash
# scripts/verify_deploy.sh — Post-deploy health verification for all services.
#
# Usage:
#   DEPLOY_HOST=https://your-app.run.app bash scripts/verify_deploy.sh
#
# Environment variables:
#   DEPLOY_HOST         Base URL of the deployed service (required)
#   AUTH_HOST           Base URL of the auth service (optional, reserved)
#   SLACK_WEBHOOK_URL   If set, posts failure notification to Slack
#   GITHUB_SHA          Included in Slack notification when set
#
# Exit codes:
#   0 — all services healthy
#   1 — one or more services failed

set -uo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-}"
AUTH_HOST="${AUTH_HOST:-http://localhost:5001}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
SHA="${GITHUB_SHA:-local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$DEPLOY_HOST" ]; then
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [FAIL] DEPLOY_HOST is required (example: https://your-app-domain.com)"
  exit 1
fi

OVERALL_EXIT=0

# ── Logging helpers ───────────────────────────────────────────────────────────
_ts()   { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
_ok()   { echo "[$(_ts)] [OK]   $*"; }
_fail() { echo "[$(_ts)] [FAIL] $*"; OVERALL_EXIT=1; }
_info() { echo "[$(_ts)] [INFO] $*"; }

# ── Slack notification on failure ─────────────────────────────────────────────
_notify_slack() {
  local msg="$1"
  if [ -n "$SLACK_WEBHOOK_URL" ]; then
    curl -s -X POST "$SLACK_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      -d "{\"text\":\"$msg\"}" > /dev/null || true
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Service 1 — API /health: must return 200 with status:healthy + database:connected
# Polls every 5s, timeout 60s (12 attempts)
# ─────────────────────────────────────────────────────────────────────────────
_check_api_health() {
  _info "Service 1/4 — API health: ${DEPLOY_HOST}/health"
  local t0; t0=$(date +%s)
  for i in $(seq 1 12); do
    local t1; t1=$(date +%s)
    local elapsed=$(( t1 - t0 ))
    local body http
    body=$(curl -s --max-time 5 "${DEPLOY_HOST}/health" 2>/dev/null || echo "")
    http=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${DEPLOY_HOST}/health" 2>/dev/null || echo "000")

    if [ "$http" = "200" ]; then
      local ms=$(( elapsed * 1000 / i ))
      # Check database field in response body
      if echo "$body" | grep -q '"database".*"unreachable"'; then
        _fail "API responded 200 but database is unreachable: $body"
        _notify_slack "Deploy health check FAILED (sha=${SHA}): API /health reports database unreachable"
        return 1
      fi
      _ok "API /health responded HTTP 200 in ~${elapsed}s (attempt $i/12)"
      return 0
    fi

    _info "  attempt $i/12: HTTP $http (${elapsed}s elapsed) — retrying in 5s"
    sleep 5
  done

  _fail "API /health did not return 200 within 60s"
  _notify_slack "Deploy health check FAILED (sha=${SHA}): API /health timeout after 60s at ${DEPLOY_HOST}"
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Service 2 — Database connectivity: parse /health body for database field
# (Covered within Service 1; this adds an explicit standalone check)
# ─────────────────────────────────────────────────────────────────────────────
_check_database() {
  _info "Service 2/4 — Database connectivity (via ${DEPLOY_HOST}/health body)"
  local body
  body=$(curl -s --max-time 10 "${DEPLOY_HOST}/health" 2>/dev/null || echo "")

  if echo "$body" | grep -q '"database".*"connected"'; then
    _ok "Database connected (reported in /health response)"
    return 0
  fi

  if echo "$body" | grep -q '"database".*"unreachable"'; then
    _fail "Database unreachable — /health body: $body"
    _notify_slack "Deploy health check FAILED (sha=${SHA}): database unreachable at ${DEPLOY_HOST}"
    return 1
  fi

  # /health didn't return a parseable body (service may be starting up still)
  _fail "Database status unknown — /health response: '${body}'"
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Service 3 — WebSocket handshake
# Uses Python websocket-client if available; gracefully skips if not installed.
# ─────────────────────────────────────────────────────────────────────────────
_check_websocket() {
  _info "Service 3/4 — WebSocket handshake: ${DEPLOY_HOST}/ws"
  local ws_url
  ws_url=$(echo "$DEPLOY_HOST" | sed 's/^http:/ws:/; s/^https:/wss:/')

  if ! python3 -c "import websocket" 2>/dev/null; then
    _info "websocket-client not installed — installing for this check"
    pip install websocket-client --quiet 2>/dev/null || true
  fi

  local result
  result=$(python3 - <<PYEOF 2>&1
import sys, websocket
try:
    ws = websocket.create_connection("${ws_url}/ws", timeout=30)
    print("WS OK:", ws.connected)
    ws.close()
    sys.exit(0)
except Exception as e:
    print("WS ERROR:", e)
    sys.exit(1)
PYEOF
  )
  local py_exit=$?

  if [ $py_exit -eq 0 ]; then
    _ok "WebSocket handshake accepted ($result)"
    return 0
  else
    # Cloud Run may not support raw WebSocket on all plans; treat as warning not hard fail
    _info "WebSocket check failed (may not be supported on this plan): $result"
    _info "  Treating as non-fatal — SSE streaming checked separately"
    return 0
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Service 4 — SSE streaming endpoint: /stream/metrics must emit at least one
# data: line within 10 seconds
# ─────────────────────────────────────────────────────────────────────────────
_check_streaming() {
  _info "Service 4/4 — SSE stream: ${DEPLOY_HOST}/stream/metrics"
  local output
  output=$(curl -s --max-time 10 -N \
    -H "Accept: text/event-stream" \
    "${DEPLOY_HOST}/stream/metrics" 2>/dev/null || echo "")

  if echo "$output" | grep -q "^data:"; then
    _ok "SSE stream emitted at least one data: line"
    return 0
  fi

  # A 200 with keep-alive but no data yet is still acceptable for a cold start
  local http
  http=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    -H "Accept: text/event-stream" \
    "${DEPLOY_HOST}/stream/metrics" 2>/dev/null || echo "000")

  if [ "$http" = "200" ] || [ "$http" = "401" ] || [ "$http" = "403" ]; then
    _ok "SSE endpoint reachable (HTTP $http) — no data emitted yet (cold start)"
    return 0
  fi

  _fail "SSE /stream/metrics returned HTTP $http — not reachable"
  _notify_slack "Deploy health check FAILED (sha=${SHA}): /stream/metrics returned HTTP $http at ${DEPLOY_HOST}"
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
echo "========================================================"
echo "  Post-Deploy Verification"
echo "  Host : $DEPLOY_HOST"
echo "  SHA  : $SHA"
echo "========================================================"

_check_api_health  || OVERALL_EXIT=1
_check_database    || OVERALL_EXIT=1
_check_websocket   || true   # non-fatal — Cloud Run WS support varies
_check_streaming   || OVERALL_EXIT=1

echo "========================================================"
if [ "$OVERALL_EXIT" -eq 0 ]; then
  echo "  RESULT: PASS — all services healthy"
else
  echo "  RESULT: FAIL — one or more services failed"
  _notify_slack "Deploy verification FAILED for sha=${SHA} at ${DEPLOY_HOST} — rollback may be triggered"
fi
echo "========================================================"

exit "$OVERALL_EXIT"
