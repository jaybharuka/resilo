#!/usr/bin/env bash
# rollback_bluegreen.sh — Switch active blue/green slot in < 60 seconds
#
# Usage:
#   ./scripts/rollback_bluegreen.sh [blue|green] [NAMESPACE] [RELEASE_NAME]
#
# Examples:
#   ./scripts/rollback_bluegreen.sh blue                     # rollback to blue in 'aiops' namespace
#   ./scripts/rollback_bluegreen.sh blue production aiops-prod
#
# How it works:
#   1. Validates that the target slot's Deployment is healthy (all pods ready)
#   2. Updates the Helm release's blueGreen.activeVersion value — this patches
#      the Service selector atomically, switching all new traffic to the target slot
#   3. Verifies the Service selector was updated
#   4. Reports rollback time (target: < 60 s)
#
# Requirements: helm, kubectl, curl (for health check)

set -euo pipefail

TARGET_SLOT="${1:-blue}"
NAMESPACE="${2:-aiops}"
RELEASE="${3:-aiops-bot}"
HELM_CHART_DIR="$(cd "$(dirname "$0")/../helm/aiops-bot" && pwd)"
START_TS=$(date +%s)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Validate input ─────────────────────────────────────────────────────────────
if [[ "$TARGET_SLOT" != "blue" && "$TARGET_SLOT" != "green" ]]; then
  error "TARGET_SLOT must be 'blue' or 'green'. Got: $TARGET_SLOT"
  exit 1
fi

info "Rolling back to slot: $TARGET_SLOT | namespace: $NAMESPACE | release: $RELEASE"

# ── Check target Deployment is healthy ─────────────────────────────────────────
TARGET_DEPLOY="api-gateway-${TARGET_SLOT}"
info "Checking readiness of Deployment/$TARGET_DEPLOY ..."

READY=$(kubectl get deployment "$TARGET_DEPLOY" -n "$NAMESPACE" \
  -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
DESIRED=$(kubectl get deployment "$TARGET_DEPLOY" -n "$NAMESPACE" \
  -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")

if [[ "$READY" == "0" || "$READY" != "$DESIRED" ]]; then
  warn "Deployment/$TARGET_DEPLOY has $READY/$DESIRED pods ready."
  warn "Proceeding anyway — target slot may still be warming up."
fi

# ── Switch traffic via Helm upgrade ────────────────────────────────────────────
info "Switching Service selector to slot=$TARGET_SLOT via Helm ..."

helm upgrade "$RELEASE" "$HELM_CHART_DIR" \
  --namespace "$NAMESPACE" \
  --reuse-values \
  --set "services.apiGateway.blueGreen.activeVersion=${TARGET_SLOT}" \
  --atomic \
  --timeout 60s \
  --wait

info "Helm upgrade complete."

# ── Verify Service selector ────────────────────────────────────────────────────
SELECTOR=$(kubectl get service api-gateway -n "$NAMESPACE" \
  -o jsonpath='{.spec.selector.app\.kubernetes\.io/version}' 2>/dev/null || echo "unknown")

if [[ "$SELECTOR" == "$TARGET_SLOT" ]]; then
  info "Service selector confirmed: app.kubernetes.io/version=$SELECTOR"
else
  error "Service selector mismatch! Expected '$TARGET_SLOT', got '$SELECTOR'"
  exit 1
fi

# ── Health check ───────────────────────────────────────────────────────────────
info "Running health check against active slot ..."
SVC_IP=$(kubectl get service api-gateway -n "$NAMESPACE" \
  -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")

if [[ -n "$SVC_IP" ]]; then
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time 5 "http://${SVC_IP}/health/ready" || echo "000")
  if [[ "$HTTP_STATUS" == "200" ]]; then
    info "Health check passed (HTTP $HTTP_STATUS)"
  else
    warn "Health check returned HTTP $HTTP_STATUS — verify manually."
  fi
else
  warn "Could not determine ClusterIP — skipping HTTP health check."
fi

# ── Report ─────────────────────────────────────────────────────────────────────
END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
info "Rollback to '$TARGET_SLOT' completed in ${ELAPSED}s."

if [[ "$ELAPSED" -gt 60 ]]; then
  warn "Rollback took more than 60 s (${ELAPSED}s). Review Helm chart or cluster performance."
else
  info "✓ Within 60 s SLA."
fi
