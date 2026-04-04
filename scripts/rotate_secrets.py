#!/usr/bin/env python3
"""Rotate core application secrets in .env with backup and restart guidance."""

from __future__ import annotations

import argparse
import base64
import secrets
import shutil
from datetime import datetime
from pathlib import Path


def _generate_fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _load_env(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f".env file not found at {path}")
    return path.read_text(encoding="utf-8").splitlines()


def _upsert_env(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            output.append(f"{prefix}{value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{prefix}{value}")
    return output


def rotate(env_path: Path) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup = env_path.with_suffix(f".env.backup.{timestamp}")
    shutil.copy2(env_path, backup)

    lines = _load_env(env_path)
    lines = _upsert_env(lines, "JWT_SECRET_KEY", secrets.token_urlsafe(48))
    lines = _upsert_env(lines, "GATEWAY_JWT_SECRET", secrets.token_urlsafe(48))
    lines = _upsert_env(lines, "ENCRYPTION_KEY", _generate_fernet_key())

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    backup = rotate(env_path)

    print(f"[OK] Rotated JWT_SECRET_KEY, GATEWAY_JWT_SECRET, and ENCRYPTION_KEY in {env_path}")
    print(f"[OK] Backup saved to: {backup}")
    print("Next steps:")
    print("1. Restart auth and core API services.")
    print("2. Revoke active user sessions (refresh tokens).")
    print("3. Redeploy dependent services that cache secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
