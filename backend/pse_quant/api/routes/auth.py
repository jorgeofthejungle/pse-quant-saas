"""
pse_quant/api/routes/auth.py — Authentication Endpoints for Members & Administrators
Separate login paths ensuring security isolation between regular investors and system operators.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_db_session
from pse_quant.services.auth_service import AuthService
from pse_quant.api.auth import get_current_user
from pse_quant.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def get_db():
    with get_db_session() as session:
        yield session


# ── Schemas ───────────────────────────────────────────────────

class MemberLoginRequest(BaseModel):
    email: str
    password: str


class MemberRegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    name: Optional[str] = None


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminProvisionRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    master_key: str
    name: Optional[str] = "System Administrator"


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ── Member Endpoints ──────────────────────────────────────────

@router.post("/member/register", response_model=AuthResponse, summary="Register member account")
def register_member(req: MemberRegisterRequest, db: Session = Depends(get_db)):
    """Creates a new investor member account and returns authentication token."""
    try:
        user, token = AuthService.register_member(
            session=db,
            email=req.email,
            password=req.password,
            name=req.name,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tier": user.tier,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/member/login", response_model=AuthResponse, summary="Member sign-in gate")
def login_member(req: MemberLoginRequest, db: Session = Depends(get_db)):
    """Authenticates investor members and returns a signed session token."""
    try:
        user, token = AuthService.authenticate_member(
            session=db,
            email=req.email,
            password=req.password,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tier": user.tier,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# ── Admin Endpoints ───────────────────────────────────────────

@router.post("/admin/login", response_model=AuthResponse, summary="Restricted System Admin sign-in gate")
def login_admin(req: AdminLoginRequest, db: Session = Depends(get_db)):
    """
    STRICTLY RESTRICTED LOGIN GATE FOR SYSTEM ADMINISTRATORS.
    Requires role='admin'. Rejects regular members.
    """
    try:
        user, token = AuthService.authenticate_admin(
            session=db,
            email=req.email,
            password=req.password,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tier": user.tier,
            },
        }
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/admin/provision", response_model=AuthResponse, summary="Provision initial administrator")
def provision_admin(req: AdminProvisionRequest, db: Session = Depends(get_db)):
    """Initial provisioning endpoint: Creates administrator account using master setup key."""
    try:
        user, token = AuthService.register_admin(
            session=db,
            email=req.email,
            password=req.password,
            master_key=req.master_key,
            name=req.name,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tier": user.tier,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Current User Profile ──────────────────────────────────────

@router.get("/me", summary="Get currently authenticated user")
def get_me(current_user: User = Depends(get_current_user)):
    """Returns profile of currently authenticated user from Bearer token."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "tier": current_user.tier,
        "status": current_user.status,
    }
