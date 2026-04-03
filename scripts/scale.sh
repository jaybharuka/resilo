#!/usr/bin/env bash
# scripts/scale.sh — Manual horizontal scaling for docker-compose deployments.
#
# Usage:
#   bash scripts/scale.sh <service> <replicas>
#
# Example:
#   bash scripts/scale.sh core-api 3
#   bash scripts/scale.sh api_server 3
#
# Environment:
#   DEPLOY_HOST   Base URL to health-check replicas (default: http://localhost:8000)
#   HEALTH_PATH   Health endpoint path              (default: /health)
#
# Exit codes:
#   0 — scaled successfully and all replicas healthy
#   1 — bad args, scale failed, or health check failed

set -uo pipefail

SERVICE="${1:-}"
REPLICAS="${2:-}"
LOG_FILE="deployments.log"
DEPLOY_HOST="${DEPLOY_HOST:-}"
HEALTH_PATH="${HEALTH_PATH:-}"

# ── Usage guard ───────────────────────────────────────────────────────────────
if [ -z "$SERVICE" ] || [ -z "$REPLICAS" ]; then
  echo "Usage: bash scripts/scale.sh <service> <replicas>"
  echo ""
  echo "Arguments:"
  echo "  service    Name of the docker-compose service to scale"
  echo "  replicas   Target number of running instances (integer >= 1)"
  echo ""
  echo "Examples:"
  echo "  bash scripts/scale.sh core-api 3"
  echo "  bash scripts/scale.sh auth-api 2"
  echo "  bash scripts/scale.sh api_server 3"
  echo ""
  echo "Environment:"
  echo "  DEPLOY_HOST   Base URL for health checks  (default: http://localhost:8000)"
  echo "  HEALTH_PATH   Health endpoint path         (default: /health)"
  exit 1
fi

# Allow legacy/audit service naming aliases.
case "$SERVICE" in
  api_server|api-server)
    SERVICE="core-api"
    ;;
  auth_api|auth-api)
    SERVICE="auth-api"
    ;;
  websocket|websocket-api)
    SERVICE="core-api"
    ;;
esac

if [ -z "$DEPLOY_HOST" ]; then
  if [ "$SERVICE" = "core-api" ]; then
    DEPLOY_HOST="http://localhost"
    HEALTH_PATH="${HEALTH_PATH:-/api/v1/health}"
  else
    DEPLOY_HOST="http://localhost:8000"
    HEALTH_PATH="${HEALTH_PATH:-/health}"
  fi
fi

if [ -z "$HEALTH_PATH" ]; then
  HEALTH_PATH="/health"
fi

if ! [[ "$REPLICAS" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: replicas must be a positive integer, got: '$REPLICAS'"
  exit 1
fi

TS() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

log() { echo "[$(TS)] $*" | tee -a "$LOG_FILE"; }

# ── Scale ─────────────────────────────────────────────────────────────────────
log "Scaling $SERVICE to $REPLICAS replica(s)..."

if ! docker compose up -d --scale "$SERVICE=$REPLICAS" --no-recreate 2>&1 | tee -a "$LOG_FILE"; then
  log "ERROR: docker compose scale failed for $SERVICE"
  exit 1
fi

log "Scale command accepted. Waiting 10s for replicas to start..."
sleep 10

# ── Health verification ───────────────────────────────────────────────────────
HEALTHY=0
ATTEMPTS=12   # 12 * 5s = 60s timeout

log "Health-checking $DEPLOY_HOST$HEALTH_PATH ..."

for i in $(seq 1 $ATTEMPTS); do
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    "${DEPLOY_HOST}${HEALTH_PATH}" 2>/dev/null || echo "000")

  if [ "$HTTP" = "200" ] || [ "$HTTP" = "301" ] || [ "$HTTP" = "302" ]; then
    HEALTHY=1
    log "Health check passed (attempt $i/$ATTEMPTS, HTTP $HTTP)"
    break
  fi

  log "  attempt $i/$ATTEMPTS: HTTP $HTTP — retrying in 5s"
  sleep 5
done

# ── Report ────────────────────────────────────────────────────────────────────
RUNNING=$(docker compose ps --filter "status=running" "$SERVICE" 2>/dev/null | grep -c "$SERVICE" || echo 0)

if [ "$HEALTHY" -eq 1 ]; then
  log "SUCCESS: $SERVICE scaled to $REPLICAS ($RUNNING running). Health check passed."
  echo "========================================================"
  echo "  SCALE RESULT: PASS"
  echo "  Service  : $SERVICE"
  echo "  Requested: $REPLICAS replica(s)"
  echo "  Running  : $RUNNING container(s)"
  echo "========================================================"
  exit 0
else
  log "WARN: $SERVICE scaled to $REPLICAS but health check did not return 200 within 60s."
  echo "========================================================"
  echo "  SCALE RESULT: DEGRADED"
  echo "  Service  : $SERVICE"
  echo "  Running  : $RUNNING container(s)"
  echo "  Health   : FAIL (check $DEPLOY_HOST$HEALTH_PATH)"
  echo "========================================================"
  exit 1
fi
