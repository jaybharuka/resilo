"""
Authorization helpers for multi-tenant access control.

Provides functions to verify org-level access for admin operations.
"""

from database import User
from fastapi import HTTPException, status


async def require_org_access(admin: User, target_org_id: str) -> None:
    """
    Verify that an admin user has access to the target organization.
    
    Admins can only manage users/resources within their own org.
    Super-admins (org_id=None) have access to all orgs.
    
    Raises HTTPException(403) if access is denied.
    """
    if admin.org_id is None:
        # Super-admin has access to all orgs
        return
    
    if admin.org_id != target_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user does not belong to this organization"
        )


async def require_admin_in_org(admin: User, org_id: str) -> None:
    """
    Verify that an admin user has admin role and belongs to the specified org.
    
    Raises HTTPException(403) if the user is not an admin or doesn't belong to the org.
    """
    if admin.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    
    await require_org_access(admin, org_id)
