#!/usr/bin/env bash
# scripts/rollback.sh — Roll back Cloud Run services to a previous image.
#
# Usage:
#   bash scripts/rollback.sh <git-sha>    roll back to a specific commit SHA
#   bash scripts/rollback.sh              roll back to SHA stored in .last_good_deploy
#
# Environment variables:
#   GCP_PROJECT       GCP project ID        (default: resilo-ai)
#   GCP_REGION        Cloud Run region      (default: us-central1)
#   ROLLBACK_SERVICE  core-api|auth-api|all (default: all)
#
# Side effects:
#   - Appends a timestamped entry to deployments.log
#   - On success: writes the rolled-back SHA to .last_good_deploy

set -euo pipefail

GCP_PROJECT="${GCP_PROJECT:-resilo-ai}"
GCP_REGION="${GCP_REGION:-us-central1}"
ROLLBACK_SERVICE="${ROLLBACK_SERVICE:-all}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAST_GOOD_FILE="${REPO_ROOT}/.last_good_deploy"
DEPLOY_LOG="${REPO_ROOT}/deployments.log"

# ── Resolve rollback target SHA ───────────────────────────────────────────────
TARGET_SHA="${1:-}"

if [ -z "$TARGET_SHA" ]; then
  if [ -f "$LAST_GOOD_FILE" ]; then
    TARGET_SHA="$(cat "$LAST_GOOD_FILE" | tr -d '[:space:]')"
    echo "No SHA provided — using .last_good_deploy: $TARGET_SHA"
  else
    echo "ERROR: No rollback target provided and .last_good_deploy does not exist."
    echo ""
    echo "Usage:"
    echo "  bash scripts/rollback.sh <git-sha>   # roll back to specific SHA"
    echo "  bash scripts/rollback.sh             # roll back to .last_good_deploy"
    echo ""
    echo "To create .last_good_deploy manually:"
    echo "  echo '<known-good-sha>' > .last_good_deploy"
    exit 1
  fi
fi

if [ -z "$TARGET_SHA" ]; then
  echo "ERROR: .last_good_deploy exists but is empty. Provide a SHA explicitly."
  exit 1
fi

echo "Rolling back to SHA: $TARGET_SHA"
echo "Services: $ROLLBACK_SERVICE"
TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ── Rollback helper ───────────────────────────────────────────────────────────
_rollback_service() {
  local service="$1"
  local image="gcr.io/${GCP_PROJECT}/${service}:${TARGET_SHA}"

  echo ""
  echo "--- Rolling back $service to $image ---"
  gcloud run deploy "$service" \
    --image "$image" \
    --region "$GCP_REGION" \
    --platform managed \
    --quiet

  # Verify with health check
  local service_url
  service_url=$(gcloud run services describe "$service" \
    --region "$GCP_REGION" \
    --format='value(status.url)')

  echo "Health-checking $service_url/health ..."
  local healthy=false
  for i in $(seq 1 12); do
    local http
    http=$(curl -s -o /dev/null -w "%{http_code}" "$service_url/health" || echo "000")
    echo "  attempt $i/12: HTTP $http"
    if [ "$http" = "200" ]; then
      healthy=true
      break
    fi
    sleep 10
  done

  if [ "$healthy" = "true" ]; then
    echo "$service rollback successful and healthy."
    echo "${TIMESTAMP} ROLLBACK OK  service=${service} sha=${TARGET_SHA}" >> "$DEPLOY_LOG"
    return 0
  else
    echo "ERROR: $service health check failed after rollback to $TARGET_SHA."
    echo "${TIMESTAMP} ROLLBACK FAIL service=${service} sha=${TARGET_SHA}" >> "$DEPLOY_LOG"
    return 1
  fi
}

# ── Execute rollback ──────────────────────────────────────────────────────────
OVERALL_EXIT=0

case "$ROLLBACK_SERVICE" in
  core-api)
    _rollback_service "core-api" || OVERALL_EXIT=1
    ;;
  auth-api)
    _rollback_service "auth-api" || OVERALL_EXIT=1
    ;;
  all|*)
    _rollback_service "core-api" || OVERALL_EXIT=1
    _rollback_service "auth-api" || OVERALL_EXIT=1
    ;;
esac

# ── Record last good deploy on success ────────────────────────────────────────
if [ "$OVERALL_EXIT" -eq 0 ]; then
  echo "$TARGET_SHA" > "$LAST_GOOD_FILE"
  echo ""
  echo "Rollback complete. .last_good_deploy updated to $TARGET_SHA"
else
  echo ""
  echo "Rollback encountered errors. Check deployments.log for details."
fi

exit "$OVERALL_EXIT"
