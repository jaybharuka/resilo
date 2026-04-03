"""
Secrets management and validation.

Ensures all required secrets are present at startup.
Provides helpers for secret rotation and versioning.
"""

import os
import logging
from typing import Dict, List, Optional

log = logging.getLogger("secrets")


# Required secrets that must be set in environment
REQUIRED_SECRETS = [
    "JWT_SECRET_KEY",
    "ENCRYPTION_KEY",
    "DATABASE_URL",
]

# Optional secrets with sensible defaults
OPTIONAL_SECRETS = {
    "ADMIN_DEFAULT_PASSWORD": "Admin@1234",
    "ENVIRONMENT": "development",
    "FRONTEND_URL": "http://localhost:3000",
    "BACKUP_DIR": "./backups",
    "BACKUP_RETENTION_DAYS": "30",
    "BACKUP_HEALTH_CHECK_HOURS": "24",
    "ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:3001,http://127.0.0.1:3000",
}


def validate_secrets() -> None:
    """
    Validate that all required secrets are set in environment.
    
    Raises:
        RuntimeError: If any required secret is missing
    """
    missing = []
    
    for secret_name in REQUIRED_SECRETS:
        if not os.getenv(secret_name):
            missing.append(secret_name)
    
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"See .env.example for required configuration."
        )
    
    log.info("All required secrets validated successfully")


def get_secret(name: str, default: Optional[str] = None) -> str:
    """
    Get a secret from environment with optional default.
    
    Args:
        name: Secret name (environment variable)
        default: Default value if not set
    
    Returns:
        Secret value
    
    Raises:
        RuntimeError: If secret not found and no default provided
    """
    value = os.getenv(name, default)
    
    if not value:
        raise RuntimeError(f"Secret '{name}' not found in environment and no default provided")
    
    return value


def get_secret_safe(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a secret from environment safely (returns None if not found).
    
    Args:
        name: Secret name (environment variable)
        default: Default value if not set
    
    Returns:
        Secret value or None
    """
    return os.getenv(name, default)


def validate_secret_format(secret_name: str, secret_value: str, min_length: int = 16) -> bool:
    """
    Validate that a secret meets minimum security requirements.
    
    Args:
        secret_name: Name of the secret (for logging)
        secret_value: The secret value to validate
        min_length: Minimum length requirement (default 16 chars)
    
    Returns:
        True if valid
    
    Raises:
        ValueError: If secret doesn't meet requirements
    """
    if not secret_value:
        raise ValueError(f"{secret_name} cannot be empty")
    
    if len(secret_value) < min_length:
        raise ValueError(f"{secret_name} must be at least {min_length} characters (got {len(secret_value)})")
    
    return True


class SecretsRotation:
    """
    Helper for managing secret rotation with versioning.
    
    Allows old and new secrets during rotation period.
    """
    
    @staticmethod
    def get_current_and_previous(current_env_var: str, previous_env_var: Optional[str] = None) -> tuple:
        """
        Get current and previous (old) secrets for rotation.
        
        Args:
            current_env_var: Environment variable for current secret
            previous_env_var: Environment variable for previous secret (optional)
        
        Returns:
            Tuple of (current_secret, previous_secret or None)
        """
        current = os.getenv(current_env_var)
        previous = os.getenv(previous_env_var) if previous_env_var else None
        
        if not current:
            raise RuntimeError(f"Current secret '{current_env_var}' not set")
        
        return current, previous
    
    @staticmethod
    def try_with_rotation(secret_name: str, validator_func, *args, **kwargs):
        """
        Try validation with current secret, fall back to previous if available.
        
        Args:
            secret_name: Name of secret being rotated
            validator_func: Function to validate with secret
            *args: Arguments to pass to validator
            **kwargs: Keyword arguments to pass to validator
        
        Returns:
            Result from validator_func
        
        Raises:
            Exception: If both current and previous secrets fail validation
        """
        current_var = f"{secret_name}"
        previous_var = f"{secret_name}_PREVIOUS"
        
        current, previous = SecretsRotation.get_current_and_previous(current_var, previous_var)
        
        # Try current secret first
        try:
            return validator_func(current, *args, **kwargs)
        except Exception as e:
            if previous:
                log.warning(f"Current {secret_name} validation failed, trying previous: {e}")
                try:
                    return validator_func(previous, *args, **kwargs)
                except Exception as e2:
                    log.error(f"Both current and previous {secret_name} failed: {e2}")
                    raise
            else:
                raise
