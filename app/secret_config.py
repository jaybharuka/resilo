"""
secret_config.py — Centralised startup secret validation for the AIOps backend.

Call validate_secrets() once at the top of each service entrypoint
(auth_api.py, core_api.py, aiops_chatbot_backend.py).

It loads the repo-root .env via python-dotenv (if available) and then
verifies every required secret is present, non-empty, and not a known-bad
placeholder value.  It raises RuntimeError immediately on failure — there
is no silent fallback.

Usage (top of each service entrypoint, before other local imports):

    from secret_config import validate_secrets
    validate_secrets("JWT_SECRET_KEY")          # auth_api, core_api, rbac consumers
    validate_secrets("JWT_SECRET_KEY", "SECRET_KEY")  # aiops_chatbot_backend
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Load .env from the repo root as early as possible so that every subsequent
# os.getenv() call — including those at module-level in imported files — sees
# the values.  We use python-dotenv when available and fall back to a minimal
# manual parser so the validator works even before dependencies are installed.
# ---------------------------------------------------------------------------
def _load_env() -> None:
    here = os.path.dirname(os.path.abspath(__file__))      # app/
    root = os.path.dirname(here)                             # repo root
    env_path = os.path.join(root, ".env")

    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass  # fall through to manual parser

    # Minimal fallback: parse KEY=VALUE lines, honour comments and quoted values
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_load_env()

# ---------------------------------------------------------------------------
# Known-bad placeholder values that indicate a secret was never configured
# ---------------------------------------------------------------------------
_BAD_VALUES: frozenset[str] = frozenset(
    {
        "",
        "dev-secret",
        "dev-secret-change-me",
        "change-me",
        "changeme",
        "secret",
        "your-secret-key",
        "YOUR_JWT_SECRET_KEY",
        "supersecret",
        "mysecret",
    }
)

# Minimum character lengths for secrets that have cryptographic strength requirements.
# JWT signing keys must be at least 32 bytes (256 bits) for HS256.
_MIN_LENGTHS: dict[str, int] = {
    "JWT_SECRET_KEY": 32,
    "GATEWAY_JWT_SECRET": 32,
    "SECRET_KEY": 32,
}


def validate_secrets(*required: str) -> None:
    """
    Verify that every key in *required is set in the environment, is not a
    known-bad placeholder, and meets the minimum length for its type.

    Raises RuntimeError with a clear, actionable message.
    Never silently falls back to an insecure default.

    Args:
        *required: Names of environment variables that must be present.

    Raises:
        RuntimeError: If any required secret is missing, is a placeholder,
                      or is shorter than the required minimum length.
    """
    missing: list[str] = []
    bad: list[str] = []
    too_short: list[str] = []

    for key in required:
        val = os.getenv(key, "")
        if not val:
            missing.append(key)
        elif val in _BAD_VALUES:
            bad.append(f"{key}={val!r}")
        elif key in _MIN_LENGTHS and len(val) < _MIN_LENGTHS[key]:
            too_short.append(
                f"{key} ({len(val)} chars, need ≥ {_MIN_LENGTHS[key]})"
            )

    lines: list[str] = []
    if missing:
        lines.append(
            "Missing secrets: " + ", ".join(missing) + "\n"
            "  → Add them to your .env file (see .env.example for format)."
        )
    if bad:
        lines.append(
            "Refusing to start with placeholder secrets: " + ", ".join(bad) + "\n"
            "  → Generate a real value with:\n"
            "      python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    if too_short:
        lines.append(
            "Secrets too short (insufficient entropy): " + ", ".join(too_short) + "\n"
            "  → Generate a strong value with:\n"
            "      python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )

    if lines:
        border = "=" * 62
        body = "\n\n".join(lines)
        msg = (
            f"\n\n{border}\n"
            f"STARTUP ABORTED — SECRETS NOT CONFIGURED\n"
            f"{border}\n"
            f"{body}\n"
            f"{border}\n"
        )
        print(msg, file=sys.stderr, flush=True)
        raise RuntimeError(msg)


def require(key: str) -> str:
    """
    Return the value of *key* from the environment, or raise immediately.
    Assumes validate_secrets() has already been called for *key*.
    """
    val = os.getenv(key, "")
    if not val or val in _BAD_VALUES:
        raise RuntimeError(
            f"Required secret '{key}' is missing or contains a placeholder value. "
            "Ensure validate_secrets() was called at startup and .env is configured."
        )
    min_len = _MIN_LENGTHS.get(key)
    if min_len and len(val) < min_len:
        raise RuntimeError(
            f"Required secret '{key}' is only {len(val)} chars — "
            f"need ≥ {min_len} for sufficient entropy. "
            "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return val
