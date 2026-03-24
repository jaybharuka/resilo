"""
vault_client.py — HashiCorp Vault secret reader for AIOps Bot.

Usage:
    from vault.vault_client import get_secret, load_secrets_into_env

    load_secrets_into_env()   # Call once at startup; populates os.environ
    secret = get_secret("secret/data/aiops/ai_apis")
"""

import os
import logging

logger = logging.getLogger("aiops.vault")

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "aiops-root-token")

# Paths → env-var mappings to auto-load at startup
_SECRET_MAP = {
    "secret/data/aiops/ai_apis": {
        "gemini_api_key": "GOOGLE_API_KEY",
    },
    "secret/data/aiops/discord": {
        "webhook_url": "DISCORD_WEBHOOK_URL",
        "bot_token":   "DISCORD_BOT_TOKEN",
    },
    "secret/data/aiops/slack": {
        "webhook_url": "SLACK_WEBHOOK_URL",
        "bot_token":   "SLACK_BOT_TOKEN",
    },
    "secret/data/aiops/app_security": {
        "jwt_secret": "JWT_SECRET_KEY",
    },
}


def get_secret(path: str) -> dict:
    """
    Read a KV v2 secret from Vault.
    Returns the `data` dict on success, empty dict on failure.
    """
    try:
        import hvac  # pip install hvac
        client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
        if not client.is_authenticated():
            logger.warning("Vault authentication failed — skipping secret load")
            return {}
        # KV v2: path format is "secret/data/<path>"
        mount, *rest = path.split("/data/", 1)
        if not rest:
            return {}
        response = client.secrets.kv.v2.read_secret_version(
            path=rest[0], mount_point=mount
        )
        return response.get("data", {}).get("data", {})
    except ImportError:
        logger.debug("hvac not installed — Vault integration disabled")
        return {}
    except Exception as exc:
        logger.warning("Vault read failed for %s: %s", path, exc)
        return {}


def load_secrets_into_env() -> int:
    """
    Load all mapped Vault secrets into os.environ.
    Only sets variables that are not already set (env file takes precedence).
    Returns the count of variables actually loaded.
    """
    loaded = 0
    for vault_path, mapping in _SECRET_MAP.items():
        data = get_secret(vault_path)
        if not data:
            continue
        for vault_key, env_key in mapping.items():
            value = data.get(vault_key)
            if value and not os.environ.get(env_key):
                os.environ[env_key] = str(value)
                logger.info("Loaded %s from Vault", env_key)
                loaded += 1
    if loaded:
        logger.info("Loaded %d secrets from Vault into environment", loaded)
    return loaded
