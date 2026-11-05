"""
pse_quant/api/auth.py — FastAPI Authentication & Role Authorization Dependencies
Secures endpoints, separating Member and Administrator access boundaries.
"""

from __future__ import annotations
import os
from typing import Optional
from fastapi import Depends, HTTPException, Security, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_db_session
from pse_quant.db.models import User
from pse_quant.services.auth_service import decode_access_token, ADMIN_MASTER_KEY

security_bearer = HTTPBearer(auto_error=False)


def get_db():
    with get_db_session() as session:
        yield session


def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Extracts and validates JWT Bearer token from Authorization header."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(auth.credentials)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
        user_id = int(user_id_str)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired or is invalid.")

    user = db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive or not found.")

    return user


def require_admin(
    x_admin_key: Optional[str] = Header(None),
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    db: Session = Depends(get_db),
) -> User | dict:
    """
    Enforces Administrator role access.
    Accepts either:
      1. A valid JWT token with role == 'admin'
      2. An X-Admin-Key header matching ADMIN_MASTER_KEY
    """
    # 1. Check direct X-Admin-Key header
    if x_admin_key and x_admin_key == ADMIN_MASTER_KEY:
        return {"id": 0, "email": "system@admin.local", "role": "admin", "tier": "admin"}

    # 2. Check JWT Bearer token
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator access required. Please sign in via the Admin Login gate.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(auth.credentials)
        role = payload.get("role")
        if role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: This action requires System Administrator privileges.",
            )
        user_id = int(payload.get("sub", 0))
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token is invalid or expired.")

    user = db.get(User, user_id)
    if not user or user.role != "admin" or user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: User is not an active administrator.")

    return user
