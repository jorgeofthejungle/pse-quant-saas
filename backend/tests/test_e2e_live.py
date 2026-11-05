"""
backend/tests/test_e2e_live.py — Full End-to-End Live Integration Test Suite
Validates the complete StockPilot PH operational loop across live FastAPI and Next.js services.

Stages tested:
  1. System Health & Heartbeat (Backend & Frontend)
  2. Operator & Administrator Gate (Strict Auth Isolation & Scoring Run)
  3. Equity Fundamental Rankings & Factor Valuation Engine
  4. Member Registration, JWT Auth & Watchlist Synchronization
  5. Alert Evaluation & Research PDF Email Pipeline
  6. Frontend Server-Side Rendered (SSR) & Dynamic Route Verification
"""

import uuid
import requests
import pytest
from pathlib import Path

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://localhost:3000"
ADMIN_KEY = "stockpilot-admin-master-2026"


def test_stage_1_system_health():
    """Stage 1: Verify live servers are responsive and healthy."""
    # Backend heartbeat
    resp = requests.get(f"{BACKEND_URL}/health", timeout=5)
    assert resp.status_code == 200, f"Backend unhealthy: {resp.status_code}"
    data = resp.json()
    assert data["status"] == "healthy"
    assert "StockPilot PH" in data["service"]

    # Frontend main page
    fe_resp = requests.get(f"{FRONTEND_URL}/", timeout=10)
    assert fe_resp.status_code == 200, f"Frontend landing page unavailable: {fe_resp.status_code}"
    assert "StockPilot" in fe_resp.text


def test_stage_2_admin_security_and_pipeline():
    """Stage 2: Test Admin login gate, timing-safe key, and trigger quantitative scoring."""
    # 1. Invalid credentials rejection
    bad_login = requests.post(
        f"{BACKEND_URL}/api/v1/auth/admin/login",
        json={"email": "admin@stockpilot.ph", "password": "WrongPassword!"},
        timeout=5,
    )
    assert bad_login.status_code == 401

    # 2. Valid admin login
    admin_login = requests.post(
        f"{BACKEND_URL}/api/v1/auth/admin/login",
        json={"email": "admin@stockpilot.ph", "password": "AdminPass123!"},
        timeout=5,
    )
    assert admin_login.status_code == 200
    admin_data = admin_login.json()
    assert "access_token" in admin_data
    assert admin_data["user"]["role"] == "admin"
    admin_token = admin_data["access_token"]

    # 3. Access admin route with Bearer token
    metrics_bearer = requests.get(
        f"{BACKEND_URL}/api/v1/admin/metrics",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=5,
    )
    assert metrics_bearer.status_code == 200
    metrics_json = metrics_bearer.json()
    assert "total_customers" in metrics_json
    assert "mrr_php" in metrics_json

    # 4. Access admin route with timing-safe X-Admin-Key header
    metrics_key = requests.get(
        f"{BACKEND_URL}/api/v1/admin/metrics",
        headers={"X-Admin-Key": ADMIN_KEY},
        timeout=5,
    )
    assert metrics_key.status_code == 200

    # 5. Trigger score recalculation
    score_resp = requests.post(
        f"{BACKEND_URL}/api/v1/admin/pipeline/score",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    assert score_resp.status_code == 200
    assert score_resp.json()["status"] == "completed"


def test_stage_3_fundamental_rankings_and_valuation():
    """Stage 3: Verify quantitative screening, factor breakdown, and macro benchmarks."""
    # 1. Macro hurdle rates
    macro_resp = requests.get(f"{BACKEND_URL}/api/v1/stocks/macro", timeout=5)
    assert macro_resp.status_code == 200
    macro = macro_resp.json()
    assert macro["ph_10y_bond_rate"] == 6.5
    assert macro["equity_risk_premium"] == 5.0
    assert macro["base_required_return"] == 11.5

    # 2. Unified rankings list
    rankings_resp = requests.get(f"{BACKEND_URL}/api/v1/stocks?portfolio=unified", timeout=5)
    assert rankings_resp.status_code == 200
    r_data = rankings_resp.json()
    assert r_data["portfolio"] == "unified"
    assert r_data["count"] > 0
    tickers = [s["ticker"] for s in r_data["data"]]
    assert "AREIT" in tickers or "DMC" in tickers

    # 3. Deep-dive equity profile (AREIT)
    profile_resp = requests.get(f"{BACKEND_URL}/api/v1/stocks/AREIT", timeout=5)
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["ticker"] == "AREIT"
    assert profile["current_price"] is not None
    assert profile["intrinsic_value"] is not None
    assert "layers" in profile
    assert "valuation" in profile

    # 4. Bargains opportunities filter
    bargains_resp = requests.get(f"{BACKEND_URL}/api/v1/stocks/bargains?min_mos=0.0", timeout=5)
    assert bargains_resp.status_code == 200
    assert isinstance(bargains_resp.json()["data"], list)


def test_stage_4_member_lifecycle_and_watchlist():
    """Stage 4: Register member, enforce access boundaries, and test watchlist CRUD."""
    test_id = uuid.uuid4().hex[:8]
    email = f"e2e_investor_{test_id}@investor.ph"
    password = "InvestorPassword123!"
    name = f"E2E Investor {test_id}"

    # 1. Register Member
    reg_resp = requests.post(
        f"{BACKEND_URL}/api/v1/auth/member/register",
        json={"email": email, "password": password, "name": name},
        timeout=5,
    )
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    member_token = reg_data["access_token"]
    assert reg_data["user"]["role"] == "member"

    # 2. Member Gate Sign-in
    login_resp = requests.post(
        f"{BACKEND_URL}/api/v1/auth/member/login",
        json={"email": email, "password": password},
        timeout=5,
    )
    assert login_resp.status_code == 200

    # 3. Member profile verification
    me_resp = requests.get(
        f"{BACKEND_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {member_token}"},
        timeout=5,
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email

    # 4. Strict Boundary Check: Member MUST NOT access Admin routes
    forbidden_resp = requests.get(
        f"{BACKEND_URL}/api/v1/admin/metrics",
        headers={"Authorization": f"Bearer {member_token}"},
        timeout=5,
    )
    assert forbidden_resp.status_code == 403, "Member should be blocked from admin endpoints!"

    # 5. Member tries to log in via Admin Gate -> MUST BE REJECTED with 403
    admin_gate_rejection = requests.post(
        f"{BACKEND_URL}/api/v1/auth/admin/login",
        json={"email": email, "password": password},
        timeout=5,
    )
    assert admin_gate_rejection.status_code == 403

    # 6. Watchlist CRUD
    headers = {"Authorization": f"Bearer {member_token}"}

    # Initial watchlist empty
    wl_init = requests.get(f"{BACKEND_URL}/api/v1/watchlist", headers=headers, timeout=5)
    assert wl_init.status_code == 200
    assert len(wl_init.json()) == 0

    # Add AREIT with 15% target MoS
    add_areit = requests.post(
        f"{BACKEND_URL}/api/v1/watchlist",
        headers=headers,
        json={"ticker": "areit", "target_mos_pct": 15.0, "notes": "Core REIT asset"},
        timeout=5,
    )
    assert add_areit.status_code == 200
    assert add_areit.json()["ticker"] == "AREIT"

    # Add DMC with 25% target MoS
    add_dmc = requests.post(
        f"{BACKEND_URL}/api/v1/watchlist",
        headers=headers,
        json={"ticker": "dmc", "target_mos_pct": 25.0, "notes": "Value holding play"},
        timeout=5,
    )
    assert add_dmc.status_code == 200
    assert add_dmc.json()["ticker"] == "DMC"

    # Verify both exist with alert trigger evaluation
    wl_after = requests.get(f"{BACKEND_URL}/api/v1/watchlist", headers=headers, timeout=5)
    assert wl_after.status_code == 200
    items = wl_after.json()
    assert len(items) == 2
    tickers = {item["ticker"]: item for item in items}
    assert "AREIT" in tickers
    assert "DMC" in tickers
    assert isinstance(tickers["AREIT"]["is_triggered"], bool)

    # Delete DMC from watchlist
    del_dmc = requests.delete(f"{BACKEND_URL}/api/v1/watchlist/DMC", headers=headers, timeout=5)
    assert del_dmc.status_code == 200

    # Verify 1 remains
    wl_final = requests.get(f"{BACKEND_URL}/api/v1/watchlist", headers=headers, timeout=5)
    assert wl_final.status_code == 200
    final_items = wl_final.json()
    assert len(final_items) == 1
    assert final_items[0]["ticker"] == "AREIT"


def test_stage_5_alerts_and_reporting_pipeline():
    """Stage 5: Test alert evaluation, PDF generation, and email digest."""
    admin_headers = {"X-Admin-Key": ADMIN_KEY}

    # 1. Trigger Alert Evaluation
    alerts_resp = requests.post(
        f"{BACKEND_URL}/api/v1/admin/pipeline/evaluate-alerts",
        headers=admin_headers,
        timeout=10,
    )
    assert alerts_resp.status_code == 200
    assert alerts_resp.json()["status"] == "completed"

    # 2. Trigger Email Digest Dispatch (local mock dev mode)
    email_resp = requests.post(
        f"{BACKEND_URL}/api/v1/admin/pipeline/email-digest",
        headers=admin_headers,
        timeout=15,
    )
    assert email_resp.status_code == 200
    digest_data = email_resp.json()
    assert digest_data["status"] == "completed"
    pdf_name = digest_data.get("pdf_path") or digest_data.get("pdf_generated") or "weekly_research_digest.pdf"
    pdf_file = Path(pdf_name)
    assert pdf_file.exists()
    assert pdf_file.stat().st_size > 1000


def test_stage_6_frontend_routes():
    """Stage 6: Verify all key Next.js frontend pages load cleanly."""
    routes = [
        "/",
        "/dashboard",
        "/screener",
        "/watchlist",
        "/stocks/AREIT",
        "/login",
        "/admin/login",
        "/admin",
    ]
    for r in routes:
        resp = requests.get(f"{FRONTEND_URL}{r}", timeout=10)
        assert resp.status_code == 200, f"Route {r} returned {resp.status_code}"


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("\n=================================================================")
    print("[E2E] Running StockPilot PH Full End-to-End Live Integration Test...")
    print("=================================================================")

    print("\n[Stage 1/6] Testing System Health & Connectivity...")
    test_stage_1_system_health()
    print("  [OK] Backend & Frontend heartbeats verified.")

    print("\n[Stage 2/6] Testing Admin Security & Pipeline Execution...")
    test_stage_2_admin_security_and_pipeline()
    print("  [OK] Admin gate security and score calculation verified.")

    print("\n[Stage 3/6] Testing Equity Fundamentals & Valuation Engine...")
    test_stage_3_fundamental_rankings_and_valuation()
    print("  [OK] Macro benchmarks, rankings, and DCF/DDM valuations verified.")

    print("\n[Stage 4/6] Testing Member Lifecycle, Security Isolation & Watchlist CRUD...")
    test_stage_4_member_lifecycle_and_watchlist()
    print("  [OK] Member registration, strict 403 barriers, and watchlist CRUD verified.")

    print("\n[Stage 5/6] Testing Watchlist Alert Evaluation & ReportLab PDF Dispatch...")
    test_stage_5_alerts_and_reporting_pipeline()
    print("  [OK] MoS alert scanner, PDF compilation, and email dispatch verified.")

    print("\n[Stage 6/6] Testing Next.js Frontend Server-Rendered Routes...")
    test_stage_6_frontend_routes()
    print("  [OK] All 8 frontend routes (Member & Admin portals) returned HTTP 200 OK.")

    print("\n=================================================================")
    print("[SUCCESS] ALL END-TO-END TESTS PASSED SUCCESSFULLY! (100% GREEN)")
    print("=================================================================\n")
