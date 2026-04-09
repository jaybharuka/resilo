import os
import logging

logger = logging.getLogger(__name__)


def require_secret(name: str) -> str:
    """Fetch a required secret from environment. Raises at startup if missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required secret '{name}' is not set. "
            f"Check your .env file or secrets manager."
        )
    return value
