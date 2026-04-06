"""
API key authentication for service-to-service calls.

Provides validation and management of API keys for internal service communication.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from database import APIKey, Organization
from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def generate_api_key() -> str:
    """Generate a random API key (32 bytes = 256 bits)."""
    return secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


async def validate_api_key(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Optional[AsyncSession] = None,
) -> tuple[Organization, APIKey]:
    """
    Validate an API key from X-API-Key header.
    
    Returns: (Organization, APIKey) tuple if valid
    Raises: HTTPException(401) if invalid or inactive
    
    Args:
        api_key: API key from X-API-Key header
        db: Database session
    
    Returns:
        Tuple of (Organization, APIKey)
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database session not available",
        )
    
    # Hash the provided key and look it up
    key_hash = hash_api_key(api_key)
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash)
    )
    api_key_record = result.scalar_one_or_none()
    
    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    if not api_key_record.is_active or api_key_record.revoked_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is inactive or revoked",
        )
    
    # Get the organization
    org_result = await db.execute(
        select(Organization).where(Organization.id == api_key_record.org_id)
    )
    org = org_result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Organization not found",
        )
    
    # Update last_used_at
    api_key_record.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    
    return org, api_key_record
