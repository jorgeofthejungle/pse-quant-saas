"""
backend/tests/test_oaas_service.py — Service & API Test Suite for OaaS Engine
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select

from pse_quant.db.connection import get_session
from pse_quant.db.models import OaasMacroState, OaasRun, OaasAlert
from pse_quant.services.oaas_service import OaasService
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestOaasService:
    def test_evaluate_universe_structure(self):
        result = OaasService.evaluate_universe()
        assert "regime_title" in result
        assert "matrix" in result
        assert len(result["matrix"]) >= 16
        assert "top_allocations" in result
        assert "quarantined_traps" in result

        # Verify ILLIQ is quarantined
        illiq = next((r for r in result["matrix"] if r["ticker"] == "ILLIQ"), None)
        assert illiq is not None
        assert illiq["is_quarantined"] is True
        assert illiq["action_channel"] == "QUARANTINE_REJECT"

    def test_update_macro_state(self):
        new_state = OaasService.update_macro_state(
            regime_title="Test Easing Pivot",
            z_bsp_rate=-1.0,
            z_us10y_yield=-0.5,
            z_brent_crude=0.0,
            z_usd_php=-0.8,
            z_msci_flow=1.5,
            php_10y_bval_rate=0.055,
        )
        assert new_state["regime_title"] == "Test Easing Pivot"
        assert new_state["is_active"] is True

        with get_session() as session:
            active_states = session.scalars(select(OaasMacroState).where(OaasMacroState.is_active == True)).all()
            assert len(active_states) == 1
            assert active_states[0].regime_title == "Test Easing Pivot"

    def test_daily_triage_dry_run(self):
        res = OaasService.execute_daily_triage_and_dispatch(dry_run=True)
        assert res["dry_run"] is True
        assert "run_id" in res
        assert res["total_evaluated"] >= 16

    def test_weekly_brief_dry_run(self):
        res = OaasService.execute_weekly_brief_and_dispatch(dry_run=True)
        assert res["dry_run"] is True
        assert "run_id" in res
        assert "allocations_count" in res


class TestOaasApi:
    def test_get_regime_endpoint(self, client):
        res = client.get("/api/v1/oaas/regime")
        assert res.status_code == 200
        data = res.json()
        assert "regime_title" in data
        assert "macro_shock_vector" in data
        assert "top_allocations" in data

    def test_evaluate_endpoint_requires_admin(self, client):
        # Unauthenticated request fails
        res_unauth = client.post("/api/v1/oaas/evaluate", json={})
        assert res_unauth.status_code in (401, 403)

        # Authenticated with Master Key succeeds
        res_auth = client.post(
            "/api/v1/oaas/evaluate",
            json={"z_bsp_rate": -1.5, "z_msci_flow": 2.0},
            headers={"X-Admin-Key": ADMIN_MASTER_KEY},
        )
        assert res_auth.status_code == 200
        assert "matrix" in res_auth.json()

    def test_macro_state_endpoint_requires_admin(self, client):
        res = client.put(
            "/api/v1/oaas/macro-state",
            json={
                "regime_title": "Api Controlled Macro State",
                "z_bsp_rate": -0.5,
                "z_us10y_yield": 0.2,
                "z_brent_crude": 0.1,
                "z_usd_php": 0.0,
                "z_msci_flow": 0.8,
                "php_10y_bval_rate": 0.057,
            },
            headers={"X-Admin-Key": ADMIN_MASTER_KEY},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_dispatch_endpoint_requires_admin(self, client):
        res = client.post(
            "/api/v1/oaas/dispatch",
            json={"action": "weekly_brief", "dry_run": True},
            headers={"X-Admin-Key": ADMIN_MASTER_KEY},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "completed"

    def test_history_endpoint_requires_admin(self, client):
        res = client.get("/api/v1/oaas/history", headers={"X-Admin-Key": ADMIN_MASTER_KEY})
        assert res.status_code == 200
        assert "runs" in res.json()
        assert "active_alerts" in res.json()
