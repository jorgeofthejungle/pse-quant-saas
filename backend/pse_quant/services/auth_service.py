"""
pse_quant/services/auth_service.py — Authentication and Security Service
Provides decoupled authentication for Members and System Administrators using
salted PBKDF2 password hashing and signed JWT tokens.
"""

from __future__ import annotations
import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pse_quant.db.models import User, Subscription
from pse_quant.services.customer_service import CustomerService

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "stockpilot-ph-quant-jwt-secret-key-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

# Master setup secret for provisioning the initial admin
ADMIN_MASTER_KEY = os.getenv("ADMIN_MASTER_KEY", "stockpilot-admin-master-2026")


def hash_password(password: str) -> str:
    """Hashes a plaintext password using PBKDF2-HMAC-SHA256 with a cryptographically secure salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${key.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Verifies a plaintext password against the stored salt$hash string."""
    if not stored_hash or "$" not in stored_hash:
        return False
    try:
        salt, expected_hex = stored_hash.split("$", 1)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return secrets.compare_digest(key.hex(), expected_hex)
    except Exception:
        return False


def create_access_token(payload: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Creates a signed JWT access token."""
    to_encode = payload.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=JWT_EXPIRATION_HOURS))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodes and validates a JWT access token. Raises jwt.PyJWTError if invalid."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


class AuthService:
    """Decoupled Authentication Service for Members and Administrators."""

    # ── Member Authentication ─────────────────────────────────

    @staticmethod
    def register_member(
        session: Session,
        email: str,
        password: str,
        name: str | None = None,
    ) -> tuple[User, str]:
        """Registers a new retail/pro member, creates subscription, and returns (user, token)."""
        clean_email = email.lower().strip()
        existing = session.scalar(select(User).where(User.email == clean_email))
        if existing:
            raise ValueError(f"Email {clean_email} is already registered.")

        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")

        user = User(
            email=clean_email,
            name=name.strip() if name else None,
            password_hash=hash_password(password),
            role="member",
            tier="free",
            status="active",
        )
        session.add(user)
        session.flush()

        # Create baseline subscription
        sub = Subscription(
            user_id=user.id,
            plan="free",
            status="active",
            amount_php=0.0,
            current_period_start=datetime.now(timezone.utc),
        )
        session.add(sub)
        session.commit()

        token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "role": "member",
            "tier": user.tier,
        })
        return user, token

    @staticmethod
    def authenticate_member(
        session: Session,
        email: str,
        password: str,
    ) -> tuple[User, str]:
        """Authenticates a member. Accepts member or admin credentials on member portal."""
        clean_email = email.lower().strip()
        user = session.scalar(select(User).where(User.email == clean_email))
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password.")

        if user.status != "active":
            raise ValueError("Account is suspended or deactivated.")

        token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "tier": user.tier,
        })
        return user, token

    # ── Admin Authentication ──────────────────────────────────

    @staticmethod
    def register_admin(
        session: Session,
        email: str,
        password: str,
        master_key: str,
        name: str | None = "System Operator",
    ) -> tuple[User, str]:
        """Registers an admin account. Requires valid master setup key."""
        if master_key != ADMIN_MASTER_KEY:
            raise ValueError("Invalid master admin provisioning key.")

        clean_email = email.lower().strip()
        user = session.scalar(select(User).where(User.email == clean_email))
        if not user:
            user = User(
                email=clean_email,
                name=name,
                password_hash=hash_password(password),
                role="admin",
                tier="admin",
                status="active",
                api_key=secrets.token_urlsafe(32),
            )
            session.add(user)
        else:
            user.password_hash = hash_password(password)
            user.role = "admin"
            user.tier = "admin"
            user.status = "active"

        session.commit()
        token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "role": "admin",
            "tier": "admin",
        })
        return user, token

    @staticmethod
    def authenticate_admin(
        session: Session,
        email: str,
        password: str,
    ) -> tuple[User, str]:
        """
        Authenticates an administrator.
        STRICT SECURITY REQUIREMENT: Only users with role='admin' can authenticate here.
        Regular members attempting to authenticate here will be strictly blocked.
        """
        clean_email = email.lower().strip()
        user = session.scalar(select(User).where(User.email == clean_email))
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid administrator credentials.")

        if user.role != "admin":
            raise PermissionError("Access denied. This portal is restricted to System Administrators only.")

        if user.status != "active":
            raise ValueError("Admin account is suspended.")

        token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "role": "admin",
            "tier": "admin",
        })
        return user, token
