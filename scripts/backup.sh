#!/usr/bin/env bash
# scripts/backup.sh — PostgreSQL/TimescaleDB backup script
#
# Reads connection details and config from environment variables (or .env).
# Run manually or via the 'backup' Docker Compose service (daily at 2am).
#
# Environment variables:
#   POSTGRES_HOST             (default: localhost)
#   POSTGRES_PORT             (default: 5432)
#   POSTGRES_DB               (default: aiops)
#   POSTGRES_USER             (default: aiops)
#   POSTGRES_PASSWORD         (required)
#   BACKUP_DIR                (default: ./backups)
#   BACKUP_RETENTION_DAYS     (default: 7)

set -euo pipefail

# ── Load .env for local (non-Docker) runs ────────────────────────────────────
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_ENV_FILE="${_SCRIPT_DIR}/../.env"
if [ -f "$_ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$_ENV_FILE"
    set +a
fi

# ── Config ────────────────────────────────────────────────────────────────────
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-aiops}"
POSTGRES_USER="${POSTGRES_USER:-aiops}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?ERROR: POSTGRES_PASSWORD is required}"
BACKUP_DIR="${BACKUP_DIR:-${_SCRIPT_DIR}/../backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz"
LOG_FILE="${BACKUP_DIR}/backup.log"

# ── Helpers ───────────────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

# ── Backup ────────────────────────────────────────────────────────────────────
log "INFO  Starting backup: db=${POSTGRES_DB} host=${POSTGRES_HOST}:${POSTGRES_PORT}"

export PGPASSWORD="$POSTGRES_PASSWORD"

if pg_dump \
        -h "$POSTGRES_HOST" \
        -p "$POSTGRES_PORT" \
        -U "$POSTGRES_USER" \
        --no-password \
        "$POSTGRES_DB" \
    | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -sh "$BACKUP_FILE" 2>/dev/null | cut -f1 || echo "?")
    log "INFO  Backup successful: ${BACKUP_FILE} (${SIZE})"
else
    log "ERROR Backup FAILED for database '${POSTGRES_DB}'"
    # Remove the empty/partial file so it is not mistaken for a valid backup.
    rm -f "$BACKUP_FILE"
    exit 1
fi

# ── Retention cleanup ─────────────────────────────────────────────────────────
DELETED=0
while IFS= read -r -d '' old_file; do
    rm -f "$old_file"
    log "INFO  Retention: deleted ${old_file}"
    DELETED=$((DELETED + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 -name "backup_*.sql.gz" \
             -mtime +"$BACKUP_RETENTION_DAYS" -print0 2>/dev/null)

if [ "$DELETED" -gt 0 ]; then
    log "INFO  Retention: removed ${DELETED} file(s) older than ${BACKUP_RETENTION_DAYS} days"
fi

log "INFO  Done."
