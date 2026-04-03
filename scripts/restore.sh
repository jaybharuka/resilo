#!/usr/bin/env bash
# scripts/restore.sh — PostgreSQL/TimescaleDB restore script
#
# Usage:
#   bash scripts/restore.sh <path/to/backup_YYYYMMDD_HHMMSS.sql.gz>
#
# Reads connection details from environment variables (or .env).
# Prompts for confirmation before touching the live database.

set -euo pipefail

# ── Usage guard ───────────────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Example:"
    echo "  $0 ./backups/backup_20260101_020000.sql.gz"
    echo ""
    echo "The script will prompt for confirmation before overwriting the database."
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

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
LOG_FILE="${BACKUP_DIR}/backup.log"

# ── Helpers ───────────────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

# ── Confirmation prompt ───────────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  WARNING: DESTRUCTIVE OPERATION                                  │"
echo "├──────────────────────────────────────────────────────────────────┤"
echo "│  Database : ${POSTGRES_DB}"
echo "│  Host     : ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "│  Restore  : ${BACKUP_FILE}"
echo "│                                                                  │"
echo "│  This will OVERWRITE all data in the live database.             │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""
read -r -p "Type 'yes' to proceed with restore: " CONFIRM
echo ""

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore aborted — database was NOT modified."
    exit 0
fi

# ── Restore ───────────────────────────────────────────────────────────────────
log "INFO  Starting restore: ${BACKUP_FILE} → ${POSTGRES_DB} on ${POSTGRES_HOST}:${POSTGRES_PORT}"

export PGPASSWORD="$POSTGRES_PASSWORD"

if gunzip -c "$BACKUP_FILE" | psql \
        -h "$POSTGRES_HOST" \
        -p "$POSTGRES_PORT" \
        -U "$POSTGRES_USER" \
        --no-password \
        -v ON_ERROR_STOP=1 \
        "$POSTGRES_DB"; then
    log "INFO  Restore successful: ${POSTGRES_DB} from ${BACKUP_FILE}"
    echo ""
    echo "Restore complete."
else
    log "ERROR Restore FAILED from ${BACKUP_FILE}"
    echo ""
    echo "Restore FAILED — check ${LOG_FILE} for details."
    exit 1
fi
