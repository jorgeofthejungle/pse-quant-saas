"""
backend/tests/test_auth.py — Unit Tests for Authentication & Admin Role Gates
"""

from __future__ import annotations
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from pse_quant.db.models import Base, User
from pse_quant.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    AuthService,
    ADMIN_MASTER_KEY,
)
from pse_quant.api.main import app
from pse_quant.api.routes.auth import get_db as get_db_auth
from pse_quant.api.routes.admin import get_db as get_db_admin
from pse_quant.api.auth import get_db as get_db_security


# ── Password & Token Crypto Tests ─────────────────────────────

def test_password_hashing():
    pwd = "SecretPassword123"
    hashed = hash_password(pwd)
    assert "$" in hashed
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False


def test_token_encoding_and_decoding():
    payload = {"sub": "42", "email": "test@example.com", "role": "member"}
    token = create_access_token(payload)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "42"
    assert decoded["email"] == "test@example.com"
    assert decoded["role"] == "member"


# ── AuthService Flow Tests ────────────────────────────────────

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_member_registration_and_login(session: Session):
    user, token = AuthService.register_member(session, email="member@investor.ph", password="password123", name="Member One")
    assert user.role == "member"
    assert user.tier == "free"

    # Authenticate
    auth_user, auth_token = AuthService.authenticate_member(session, email="member@investor.ph", password="password123")
    assert auth_user.id == user.id

    # Wrong password
    with pytest.raises(ValueError, match="Invalid email or password"):
        AuthService.authenticate_member(session, email="member@investor.ph", password="wrong")


def test_admin_registration_and_strict_security_boundary(session: Session):
    # Member registration
    member, _ = AuthService.register_member(session, email="regular@investor.ph", password="password123")

    # Member tries to log in via Admin Gate -> MUST BE REJECTED
    with pytest.raises(PermissionError, match="restricted to System Administrators"):
        AuthService.authenticate_admin(session, email="regular@investor.ph", password="password123")

    # Admin registration with invalid master key -> FAILS
    with pytest.raises(ValueError, match="Invalid master admin provisioning key"):
        AuthService.register_admin(session, email="admin@stockpilot.ph", password="adminpassword123", master_key="wrong_key")

    # Admin registration with valid master key -> SUCCEEDS
    admin, token = AuthService.register_admin(session, email="admin@stockpilot.ph", password="adminpassword123", master_key=ADMIN_MASTER_KEY)
    assert admin.role == "admin"

    # Admin authentication -> SUCCEEDS
    auth_admin, admin_token = AuthService.authenticate_admin(session, email="admin@stockpilot.ph", password="adminpassword123")
    assert auth_admin.id == admin.id
    assert auth_admin.role == "admin"


# ── API Endpoint & Route Guard Tests ──────────────────────────

@pytest.fixture
def client_with_auth_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)

    # Seed 1 member and 1 admin
    AuthService.register_member(session, email="user@investor.ph", password="userpass123", name="Regular User")
    AuthService.register_admin(session, email="operator@stockpilot.ph", password="adminpass123", master_key=ADMIN_MASTER_KEY, name="Operator")

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db_auth] = override_db
    app.dependency_overrides[get_db_admin] = override_db
    app.dependency_overrides[get_db_security] = override_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    session.close()


def test_api_member_and_admin_login_separation(client_with_auth_db: TestClient):
    # 1. Member logs into Member Gate
    resp = client_with_auth_db.post("/api/v1/auth/member/login", json={"email": "user@investor.ph", "password": "userpass123"})
    assert resp.status_code == 200
    member_data = resp.json()
    member_token = member_data["access_token"]
    assert member_data["user"]["role"] == "member"

    # 2. Member tries to log into Admin Gate -> MUST RETURN 403 Forbidden
    bad_admin_resp = client_with_auth_db.post("/api/v1/auth/admin/login", json={"email": "user@investor.ph", "password": "userpass123"})
    assert bad_admin_resp.status_code == 403

    # 3. Admin logs into Admin Gate -> SUCCEEDS
    admin_resp = client_with_auth_db.post("/api/v1/auth/admin/login", json={"email": "operator@stockpilot.ph", "password": "adminpass123"})
    assert admin_resp.status_code == 200
    admin_data = admin_resp.json()
    admin_token = admin_data["access_token"]
    assert admin_data["user"]["role"] == "admin"

    # 4. Access Admin Protected Route WITHOUT token -> 401 Unauthorized
    unauth_resp = client_with_auth_db.get("/api/v1/admin/metrics")
    assert unauth_resp.status_code == 401

    # 5. Access Admin Protected Route WITH MEMBER token -> 403 Forbidden
    forbidden_resp = client_with_auth_db.get("/api/v1/admin/metrics", headers={"Authorization": f"Bearer {member_token}"})
    assert forbidden_resp.status_code == 403

    # 6. Access Admin Protected Route WITH ADMIN token -> 200 OK
    ok_resp = client_with_auth_db.get("/api/v1/admin/metrics", headers={"Authorization": f"Bearer {admin_token}"})
    assert ok_resp.status_code == 200
    assert "total_customers" in ok_resp.json()

    # 7. Access Admin Protected Route WITH X-Admin-Key Header -> 200 OK
    key_resp = client_with_auth_db.get("/api/v1/admin/metrics", headers={"X-Admin-Key": ADMIN_MASTER_KEY})
    assert key_resp.status_code == 200
