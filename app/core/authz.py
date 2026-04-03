"""
Authorization helpers for org-scoped access control.

Ensures users can only access/modify data within their organization.
"""

from fastapi import HTTPException, status
from database import User


async def require_org_access(user: User, org_id: str) -> None:
    """
    Verify that a user has access to an organization.
    
    Raises HTTPException(403) if user does not belong to the organization.
    
    Args:
        user: Authenticated user
        org_id: Organization ID to check access for
    
    Raises:
        HTTPException: 403 Forbidden if user lacks access
    """
    if not user.org_id or user.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization",
        )


async def require_admin_in_org(user: User, org_id: str) -> None:
    """
    Verify that a user is an admin in a specific organization.
    
    Raises HTTPException(403) if user is not an admin or doesn't belong to org.
    
    Args:
        user: Authenticated user
        org_id: Organization ID to check admin access for
    
    Raises:
        HTTPException: 403 Forbidden if user is not an admin in the org
    """
    await require_org_access(user, org_id)
    
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be an admin to perform this action",
        )
