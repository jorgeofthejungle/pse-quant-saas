"""
backend/tests/test_rate_limiter.py — Automated Verification of Inbound API Rate Limiting
========================================================================================
Validates that SlowAPI rate limiting enforces strict burst/minute limits on:
1. Member authentication (/api/v1/auth/member/login -> 5/min)
2. Admin provisioning (/api/v1/auth/admin/provision -> 5/min)
3. Calculation & OaaS dispatch (/api/v1/oaas/dispatch -> 10/min)
4. Client IP isolation via X-Forwarded-For headers
5. 429 Too Many Requests response schema with Retry-After header
"""

import pytest
from fastapi.testclient import TestClient
from pse_quant.api.main import app
from pse_quant.services.auth_service import ADMIN_MASTER_KEY


@pytest.fixture
def client():
    return TestClient(app)


class TestApiRateLimiter:
    def test_auth_member_login_rate_limit_and_ip_isolation(self, client):
        """
        Tests that /auth/member/login is strictly capped at 5 requests/minute per client IP,
        and that a second distinct IP remains unblocked.
        """
        ip_a = "203.0.113.10"
        ip_b = "203.0.113.20"

        # Client A sends 5 login attempts (should return 401 Unauthorized, not 429)
        for i in range(5):
            res = client.post(
                "/api/v1/auth/member/login",
                json={"email": f"attacker_{i}@test.ph", "password": "wrongpassword"},
                headers={"X-Forwarded-For": ip_a},
            )
            assert res.status_code == 401, f"Attempt {i+1} should be 401 Unauthorized, got {res.status_code}"

        # 6th attempt from Client A must trigger 429 Too Many Requests
        res_blocked = client.post(
            "/api/v1/auth/member/login",
            json={"email": "attacker_6@test.ph", "password": "wrongpassword"},
            headers={"X-Forwarded-For": ip_a},
        )
        assert res_blocked.status_code == 429
        data = res_blocked.json()
        assert data["error"] == "TooManyRequests"
        assert "Rate limit exceeded" in data["message"]
        assert data["path"] == "/api/v1/auth/member/login"
        assert res_blocked.headers.get("Retry-After") == "60"

        # Client B sends a login attempt from a different IP -> should NOT be blocked (401, not 429)
        res_b = client.post(
            "/api/v1/auth/member/login",
            json={"email": "legit_user@test.ph", "password": "wrongpassword"},
            headers={"X-Forwarded-For": ip_b},
        )
        assert res_b.status_code == 401

    def test_admin_provision_rate_limit(self, client):
        """
        Tests that /auth/admin/provision is strictly capped at 5 attempts/minute.
        """
        ip = "198.51.100.55"

        for i in range(5):
            res = client.post(
                "/api/v1/auth/admin/provision",
                json={
                    "email": f"admin_candidate_{i}@test.ph",
                    "password": "Password123!",
                    "master_key": "wrong_key",
                },
                headers={"X-Forwarded-For": ip},
            )
            assert res.status_code in (400, 401)

        # 6th attempt triggers 429
        res_blocked = client.post(
            "/api/v1/auth/admin/provision",
            json={
                "email": "admin_candidate_6@test.ph",
                "password": "Password123!",
                "master_key": "wrong_key",
            },
            headers={"X-Forwarded-For": ip},
        )
        assert res_blocked.status_code == 429
        assert res_blocked.json()["error"] == "TooManyRequests"

    def test_oaas_dispatch_rate_limit(self, client):
        """
        Tests that /oaas/dispatch calculation trigger is capped at 10 requests/minute.
        """
        ip = "192.0.2.77"

        # Send 10 authorized dry-run dispatch requests
        for i in range(10):
            res = client.post(
                "/api/v1/oaas/dispatch",
                json={"action": "weekly_brief", "dry_run": True},
                headers={
                    "X-Admin-Key": ADMIN_MASTER_KEY,
                    "X-Forwarded-For": ip,
                },
            )
            assert res.status_code == 200, f"Dispatch {i+1} failed with status {res.status_code}"

        # 11th dispatch must be rejected with 429 Too Many Requests
        res_blocked = client.post(
            "/api/v1/oaas/dispatch",
            json={"action": "weekly_brief", "dry_run": True},
            headers={
                "X-Admin-Key": ADMIN_MASTER_KEY,
                "X-Forwarded-For": ip,
            },
        )
        assert res_blocked.status_code == 429
        data = res_blocked.json()
        assert data["error"] == "TooManyRequests"
        assert res_blocked.headers.get("Retry-After") == "60"
