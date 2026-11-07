"""
backend/pse_quant/api/routes/oaas.py — FastAPI Endpoints for PSE OaaS & Causal Alert Engine
========================================================================================
Exposes macro regime status, dry-run simulation, state overrides, and email dispatch.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Security, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from pse_quant.db.connection import get_db_session
from pse_quant.db.models import OaasMacroState, OaasRun, OaasAlert
from pse_quant.services.oaas_service import OaasService
from pse_quant.api.auth import require_admin, security_bearer, decode_access_token
from pse_quant.api.limiter import limiter

router = APIRouter(prefix="/oaas", tags=["oaas"])


def get_db():
    with get_db_session() as session:
        yield session


# ── Pydantic Request & Response Schemas ───────────────────────

class MacroStateUpdateRequest(BaseModel):
    regime_title: str = Field(..., min_length=3, max_length=120, description="Descriptive macro regime title")
    z_bsp_rate: float = Field(0.0, ge=-10.0, le=10.0, description="BSP Policy Rate surprise Z-score")
    z_us10y_yield: float = Field(0.0, ge=-10.0, le=10.0, description="US 10-Year Treasury Yield surge Z-score")
    z_brent_crude: float = Field(0.0, ge=-10.0, le=10.0, description="Global Brent Crude Oil price shock Z-score")
    z_usd_php: float = Field(0.0, ge=-10.0, le=10.0, description="USD/PHP foreign exchange rate shock Z-score")
    z_msci_flow: float = Field(0.0, ge=-10.0, le=10.0, description="MSCI EM Foreign Portfolio flow shock Z-score")
    php_10y_bval_rate: float = Field(0.0585, ge=0.001, le=0.50, description="Benchmark PHP 10-Year Sovereign BVAL Yield")
    metadata_json: Optional[Dict[str, Any]] = None


class DispatchTriggerRequest(BaseModel):
    action: str = Field(..., pattern="^(daily_triage|weekly_brief)$", description="Action to trigger: 'daily_triage' or 'weekly_brief'")
    dry_run: bool = Field(False, description="Set true to simulate execution without sending real emails")


class MacroEvaluationRequest(BaseModel):
    z_bsp_rate: Optional[float] = Field(None, ge=-10.0, le=10.0)
    z_us10y_yield: Optional[float] = Field(None, ge=-10.0, le=10.0)
    z_brent_crude: Optional[float] = Field(None, ge=-10.0, le=10.0)
    z_usd_php: Optional[float] = Field(None, ge=-10.0, le=10.0)
    z_msci_flow: Optional[float] = Field(None, ge=-10.0, le=10.0)
    php_10y_bval_rate: Optional[float] = Field(None, ge=0.001, le=0.50)
    active_subscribers: Optional[int] = Field(None, ge=1, le=1_000_000)
    target_ticket_php: Optional[float] = Field(None, ge=100.0, le=100_000_000.0)


# ── Route Handlers ────────────────────────────────────────────

@router.get("/regime", summary="Get active Macro Regime and top friction-cleared allocations")
@limiter.limit("120/minute")
def get_current_regime(
    request: Request,
    auth=Security(security_bearer),
    db: Session = Depends(get_db),
):
    """
    Returns current active macro regime, standardized Z-scores, benchmark BVAL yield,
    and top friction-cleared recommendations. If authenticated as Pro, includes discrete ticket sizing.
    """
    is_pro = False
    if auth and auth.credentials:
        try:
            payload = decode_access_token(auth.credentials)
            tier = payload.get("tier", "free")
            role = payload.get("role", "member")
            if tier in ("pro", "institutional") or role == "admin":
                is_pro = True
        except Exception:
            pass

    state = OaasService.get_active_macro_state(db)
    eval_result = OaasService.evaluate_universe(state.id)

    # Filter top allocations for response
    allocations_output = []
    for a in eval_result["top_allocations"]:
        item = {
            "ticker": a["ticker"],
            "name": a["name"],
            "sector": a["sector"],
            "price": a["price"],
            "board_lot": a["board_lot"],
            "net_hurdle_pct": a["net_hurdle_pct"],
            "friction_bps": a["friction_bps"],
            "action_channel": a["action_channel"],
        }
        if is_pro:
            item.update({
                "executable_shares": a["executable_shares"],
                "executable_ticket_php": a["executable_ticket_php"],
                "limit_low": a["limit_low"],
                "limit_high": a["limit_high"],
                "stop_loss": a["stop_loss"],
                "crowd_participation_pct": a["actual_participation_ratio"],
            })
        allocations_output.append(item)

    return {
        "regime_title": state.regime_title,
        "is_pro_access": is_pro,
        "macro_shock_vector": {
            "z_bsp_rate": state.z_bsp_rate,
            "z_us10y_yield": state.z_us10y_yield,
            "z_brent_crude": state.z_brent_crude,
            "z_usd_php": state.z_usd_php,
            "z_msci_flow": state.z_msci_flow,
            "php_10y_bval_rate": state.php_10y_bval_rate,
        },
        "top_allocations": allocations_output,
        "quarantined_traps_count": len(eval_result["quarantined_traps"]),
        "updated_at": state.updated_at or state.created_at,
    }


@router.post("/evaluate", summary="Run dry-run simulation of the Causal Alert Matrix")
@limiter.limit("30/minute")
def dry_run_evaluation(
    request: Request,
    req: MacroEvaluationRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Simulates quantitative triage across all benchmark equities with custom shock vector."""
    state = OaasService.get_active_macro_state(db)
    # Temporary mock or override state if requested
    temp_state = None
    if any(v is not None for v in [req.z_bsp_rate, req.z_us10y_yield, req.z_brent_crude, req.z_usd_php, req.z_msci_flow, req.php_10y_bval_rate]):
        temp_state = OaasMacroState(
            regime_title=state.regime_title + " (Simulation)",
            z_bsp_rate=req.z_bsp_rate if req.z_bsp_rate is not None else state.z_bsp_rate,
            z_us10y_yield=req.z_us10y_yield if req.z_us10y_yield is not None else state.z_us10y_yield,
            z_brent_crude=req.z_brent_crude if req.z_brent_crude is not None else state.z_brent_crude,
            z_usd_php=req.z_usd_php if req.z_usd_php is not None else state.z_usd_php,
            z_msci_flow=req.z_msci_flow if req.z_msci_flow is not None else state.z_msci_flow,
            php_10y_bval_rate=req.php_10y_bval_rate if req.php_10y_bval_rate is not None else state.php_10y_bval_rate,
        )
        db.add(temp_state)
        db.flush()

    eval_result = OaasService.evaluate_universe(
        macro_state_or_id=temp_state.id if temp_state else state.id,
        active_subscribers_override=req.active_subscribers,
        target_ticket_override=req.target_ticket_php,
    )
    return eval_result


@router.put("/macro-state", summary="Update and activate new Macro Regime state")
@limiter.limit("20/minute")
def update_macro_state(
    request: Request,
    req: MacroStateUpdateRequest,
    admin=Depends(require_admin),
):
    """Persists a new active macro regime state and deactivates prior states."""
    new_state = OaasService.update_macro_state(
        regime_title=req.regime_title,
        z_bsp_rate=req.z_bsp_rate,
        z_us10y_yield=req.z_us10y_yield,
        z_brent_crude=req.z_brent_crude,
        z_usd_php=req.z_usd_php,
        z_msci_flow=req.z_msci_flow,
        php_10y_bval_rate=req.php_10y_bval_rate,
        metadata_json=req.metadata_json,
        source="admin_override",
    )
    return {
        "status": "success",
        "message": f"Macro state updated to '{req.regime_title}'.",
        "macro_state": new_state,
    }


@router.post("/dispatch", summary="Manually trigger Weekly Brief or Daily Triage broadcast")
@limiter.limit("10/minute")
def trigger_dispatch(
    request: Request,
    req: DispatchTriggerRequest,
    admin=Depends(require_admin),
):
    """Executes either Sunday Weekly Regime Brief or Daily Causal Shock Triage."""
    if req.action == "weekly_brief":
        res = OaasService.execute_weekly_brief_and_dispatch(dry_run=req.dry_run)
    elif req.action == "daily_triage":
        res = OaasService.execute_daily_triage_and_dispatch(dry_run=req.dry_run)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: '{req.action}'. Expected 'weekly_brief' or 'daily_triage'.")

    return {
        "status": "completed",
        "action": req.action,
        "dry_run": req.dry_run,
        "result": res,
    }


@router.get("/history", summary="Fetch historical OaaS runs and active alert cooldowns")
@limiter.limit("60/minute")
def get_oaas_history(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Returns recent evaluation runs and active alert throttle cooldowns."""
    runs = db.scalars(
        select(OaasRun).order_by(desc(OaasRun.created_at)).limit(limit)
    ).all()

    active_alerts = db.scalars(
        select(OaasAlert).order_by(desc(OaasAlert.dispatched_at)).limit(limit)
    ).all()

    return {
        "runs": [
            {
                "id": r.id,
                "run_type": r.run_type,
                "regime_title": r.regime_title,
                "tickers_evaluated": r.tickers_evaluated_count,
                "alerts_triggered": r.alerts_triggered_count,
                "emails_dispatched": r.dispatched_emails_count,
                "created_at": r.created_at,
            }
            for r in runs
        ],
        "active_alerts": [
            {
                "id": a.id,
                "ticker": a.ticker,
                "alert_type": a.alert_type,
                "direction": a.direction,
                "price": a.reference_price,
                "displacement_pct": a.displacement_pct,
                "gate_threshold_pct": a.gate_threshold_pct,
                "net_hurdle_pct": a.net_hurdle_pct,
                "cooldown_until": a.cooldown_until,
                "status": a.status,
                "dispatched_at": a.dispatched_at,
            }
            for a in active_alerts
        ],
    }
