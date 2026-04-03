"""
config/env_validator.py -- Startup environment validation for all AIOps entry points.

Call validate_environment() as the very first thing in every service entry point
before any other imports that read os.getenv() at module level.

Exit codes:
    0 -- all required vars present, optional defaults applied
    1 -- one or more required vars missing (printed to stderr, process exits)

Usage:
    # At the top of api_server.py / auth_api.py / core_api.py
    from config.env_validator import validate_environment
    validate_environment()
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Required vars -- app refuses to start if any are absent or empty.
# Tuple: (VAR_NAME, human-readable description of what it is used for)
# ---------------------------------------------------------------------------
REQUIRED_ENV_VARS: list[tuple[str, str]] = [
    ("DATABASE_URL",           "PostgreSQL connection string (asyncpg format)"),
    ("JWT_SECRET_KEY",         "Secret key for signing JWT tokens (min 32 chars)"),
    ("ADMIN_DEFAULT_PASSWORD", "Initial admin account password set on first startup"),
    ("ALLOWED_ORIGINS",        "Comma-separated list of allowed CORS origins"),
    ("BACKUP_DIR",             "Directory path for database backups"),
    ("DEPLOY_HOST",            "Production hostname used by post-deploy health checks"),
]

# ---------------------------------------------------------------------------
# Optional vars -- silently applied if absent so every os.getenv() caller
# sees a consistent value without scattering defaults across the codebase.
# Tuple: (VAR_NAME, default_value)
# ---------------------------------------------------------------------------
OPTIONAL_ENV_VARS_WITH_DEFAULTS: list[tuple[str, str]] = [
    ("LOCKOUT_DURATION_MINUTES", "15"),
    ("MAX_FAILED_ATTEMPTS",      "5"),
    ("WS_QUEUE_MAX_SIZE",        "100"),
    ("MAX_CONNECTED_CLIENTS",    "50"),
    ("SSE_HEARTBEAT_SECONDS",    "30"),
    ("DB_CONNECT_RETRIES",       "5"),
    ("DB_CONNECT_RETRY_DELAY",   "3"),
    ("BACKUP_RETENTION_DAYS",    "7"),
]


def validate_environment() -> None:
    """
    Check that every variable in REQUIRED_ENV_VARS is set and non-empty.
    Apply defaults for OPTIONAL_ENV_VARS_WITH_DEFAULTS.

    Exits with code 1 immediately if any required variable is missing.
    Call this before any other import that reads os.getenv() at module level.
    """
    missing: list[str] = []
    for var, description in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            missing.append(f"  {var}: {description}")

    if missing:
        print(
            "ERROR: Missing required environment variables:\n" +
            "\n".join(missing) +
            "\n\nAdd these to your .env file and restart.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    for var, default in OPTIONAL_ENV_VARS_WITH_DEFAULTS:
        if not os.getenv(var):
            os.environ[var] = default

    print("Environment validated. All required vars present.", flush=True)
