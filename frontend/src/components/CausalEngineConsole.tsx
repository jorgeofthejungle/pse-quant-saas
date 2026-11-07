'use client';

import React, { useState, useEffect } from 'react';
import { oaasApi } from '@/lib/api';

export function CausalEngineConsole() {
  const [regimeTitle, setRegimeTitle] = useState('Neutral-to-Dovish Macro Drift');
  const [zBsp, setZBsp] = useState(0.0);
  const [zUs10y, setZUs10y] = useState(0.4);
  const [zBrent, setZBrent] = useState(-0.2);
  const [zUsdPhp, setZUsdPhp] = useState(0.5);
  const [zMsci, setZMsci] = useState(0.3);
  const [bvalRate, setBvalRate] = useState(5.85);

  const [simResults, setSimResults] = useState<any | null>(null);
  const [history, setHistory] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  useEffect(() => {
    loadActiveStateAndHistory();
  }, []);

  async function loadActiveStateAndHistory() {
    try {
      const reg = await oaasApi.getRegime();
      if (reg) {
        setRegimeTitle(reg.regime_title);
        setZBsp(reg.macro_shock_vector.z_bsp_rate);
        setZUs10y(reg.macro_shock_vector.z_us10y_yield);
        setZBrent(reg.macro_shock_vector.z_brent_crude);
        setZUsdPhp(reg.macro_shock_vector.z_usd_php);
        setZMsci(reg.macro_shock_vector.z_msci_flow);
        setBvalRate(Number((reg.macro_shock_vector.php_10y_bval_rate * 100).toFixed(2)));
      }
      const hist = await oaasApi.getHistory();
      setHistory(hist);
    } catch (err) {
      console.warn('Failed to load initial OaaS state:', err);
    }
  }

  async function handleSimulate() {
    setLoading(true);
    setActionMessage(null);
    try {
      const res = await oaasApi.evaluate({
        z_bsp_rate: zBsp,
        z_us10y_yield: zUs10y,
        z_brent_crude: zBrent,
        z_usd_php: zUsdPhp,
        z_msci_flow: zMsci,
        php_10y_bval_rate: bvalRate / 100.0,
      });
      setSimResults(res);
      setActionMessage('Dry-run simulation executed successfully.');
    } catch (err: any) {
      setActionMessage(`Simulation error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveState() {
    setLoading(true);
    setActionMessage(null);
    try {
      await oaasApi.updateMacroState({
        regime_title: regimeTitle,
        z_bsp_rate: zBsp,
        z_us10y_yield: zUs10y,
        z_brent_crude: zBrent,
        z_usd_php: zUsdPhp,
        z_msci_flow: zMsci,
        php_10y_bval_rate: bvalRate / 100.0,
      });
      setActionMessage(`Active Macro State updated to '${regimeTitle}'!`);
      loadActiveStateAndHistory();
    } catch (err: any) {
      setActionMessage(`Failed to update state: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleDispatch(action: 'weekly_brief' | 'daily_triage', dryRun: boolean) {
    if (!dryRun && typeof window !== 'undefined') {
      const confirmed = window.confirm(
        `CRITICAL NOTICE: You are triggering a LIVE subscriber email broadcast for '${action}'. Proceed with live dispatch?`
      );
      if (!confirmed) {
        return;
      }
    }
    setLoading(true);
    setActionMessage(null);
    try {
      const res = await oaasApi.dispatch(action, dryRun);
      setActionMessage(
        `Dispatched ${action} (dryRun=${dryRun}): ${JSON.stringify(res.result)}`
      );
      loadActiveStateAndHistory();
    } catch (err: any) {
      setActionMessage(`Dispatch failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl mb-8">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-3">
        <div>
          <span className="text-xs uppercase font-bold text-sky-400 tracking-wider">
            Operator Console / Mission Control
          </span>
          <h2 className="text-xl font-bold text-white mt-0.5">
            PSE Causal Alert Engine & Macro Triage Controller
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleDispatch('daily_triage', true)}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-slate-800 text-slate-200 hover:bg-slate-700 transition"
          >
            Dry-Run Triage
          </button>
          <button
            onClick={() => handleDispatch('weekly_brief', true)}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-slate-800 text-slate-200 hover:bg-slate-700 transition"
          >
            Dry-Run Weekly
          </button>
          <button
            onClick={() => handleDispatch('daily_triage', false)}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-rose-600 hover:bg-rose-500 text-white transition shadow"
          >
            ⚡ Live Triage Broadcast
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className="my-4 p-3 bg-slate-950 border border-sky-800 text-sky-300 text-sm rounded font-mono">
          {actionMessage}
        </div>
      )}

      {/* Macro State Parameters Form */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 my-6">
        <div className="md:col-span-2 space-y-3">
          <div>
            <label className="text-xs uppercase font-bold text-slate-400">Regime Headline</label>
            <input
              type="text"
              value={regimeTitle}
              onChange={(e) => setRegimeTitle(e.target.value)}
              className="w-full mt-1 bg-slate-950 border border-slate-800 rounded p-2 text-sm text-white focus:outline-none focus:border-sky-500 font-medium"
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-[11px] uppercase font-semibold text-slate-400">BSP Policy (Z)</label>
              <input
                type="number"
                step="0.1"
                value={zBsp}
                onChange={(e) => setZBsp(parseFloat(e.target.value) || 0)}
                className="w-full mt-1 bg-slate-950 border border-slate-800 rounded p-1.5 text-sm text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] uppercase font-semibold text-slate-400">US 10Y Yield (Z)</label>
              <input
                type="number"
                step="0.1"
                value={zUs10y}
                onChange={(e) => setZUs10y(parseFloat(e.target.value) || 0)}
                className="w-full mt-1 bg-slate-950 border border-slate-800 rounded p-1.5 text-sm text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] uppercase font-semibold text-slate-400">Brent Crude (Z)</label>
              <input
                type="number"
                step="0.1"
                value={zBrent}
                onChange={(e) => setZBrent(parseFloat(e.target.value) || 0)}
                className="w-full mt-1 bg-slate-950 border border-slate-800 rounded p-1.5 text-sm text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] uppercase font-semibold text-slate-400">USD/PHP FX (Z)</label>
              <input
                type="number"
                step="0.1"
                value={zUsdPhp}
                onChange={(e) => setZUsdPhp(parseFloat(e.target.value) || 0)}
                className="w-full mt-1 bg-slate-950 border border-slate-800 rounded p-1.5 text-sm text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] uppercase font-semibold text-slate-400">MSCI EM Flow (Z)</label>
              <input
                type="number"
                step="0.1"
                value={zMsci}
                onChange={(e) => setZMsci(parseFloat(e.target.value) || 0)}
                className="w-full mt-1 bg-slate-950 border border-slate-800 rounded p-1.5 text-sm text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] uppercase font-semibold text-slate-400">PHP 10Y BVAL (%)</label>
              <input
                type="number"
                step="0.05"
                value={bvalRate}
                onChange={(e) => setBvalRate(parseFloat(e.target.value) || 0)}
                className="w-full mt-1 bg-slate-950 border border-slate-800 rounded p-1.5 text-sm text-white font-mono"
              />
            </div>
          </div>
        </div>

        <div className="flex flex-col justify-end gap-2 bg-slate-950/60 p-4 rounded border border-slate-800/80">
          <button
            onClick={handleSimulate}
            disabled={loading}
            className="w-full py-2 px-4 rounded bg-sky-600 hover:bg-sky-500 text-white font-semibold text-sm transition shadow"
          >
            {loading ? 'Evaluating...' : '▶ Run Matrix Simulation'}
          </button>
          <button
            onClick={handleSaveState}
            disabled={loading}
            className="w-full py-2 px-4 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition shadow"
          >
            💾 Activate & Persist Macro State
          </button>
        </div>
      </div>

      {/* Simulation Results Matrix */}
      {simResults && (
        <div className="mt-6 border-t border-slate-800 pt-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-bold uppercase text-white tracking-wider">
              Simulation Readout: {simResults.matrix?.length || 0} Equities Tested
            </h3>
            <span className="text-xs text-slate-400 font-mono">
              Active Subscribers: {simResults.active_subscribers} | Target: ₱{simResults.target_ticket_php?.toLocaleString()}
            </span>
          </div>

          <div className="overflow-x-auto rounded border border-slate-800">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950 text-slate-400 uppercase">
                <tr>
                  <th className="p-2">Ticker</th>
                  <th className="p-2">Ref Price</th>
                  <th className="p-2">MDTV (M)</th>
                  <th className="p-2">Friction</th>
                  <th className="p-2">Macro Disp</th>
                  <th className="p-2">Factor Alpha</th>
                  <th className="p-2">Total Disp</th>
                  <th className="p-2">Gate (2F+1.5σ)</th>
                  <th className="p-2">Action Channel</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 bg-slate-950/40">
                {simResults.matrix?.map((r: any) => {
                  const isQuarantine = r.is_quarantined;
                  const isAlert = r.action_channel.includes('ALERT') || r.action_channel.includes('WARNING');
                  return (
                    <tr
                      key={r.ticker}
                      className={
                        isQuarantine
                          ? 'bg-rose-950/20 text-rose-300'
                          : isAlert
                          ? 'bg-sky-950/20 text-sky-200'
                          : 'text-slate-300'
                      }
                    >
                      <td className="p-2 font-bold">{r.ticker}</td>
                      <td className="p-2">₱{r.price.toFixed(2)}</td>
                      <td className="p-2">₱{(r.mdtv_20_php / 1e6).toFixed(1)}M</td>
                      <td className="p-2">{r.friction_bps.toFixed(0)} bps</td>
                      <td className="p-2">{(r.macro_disp_pct * 100).toFixed(2)}%</td>
                      <td className="p-2">{(r.factor_alpha_pct * 100).toFixed(2)}%</td>
                      <td className="p-2 font-semibold">{(r.total_disp_pct * 100).toFixed(2)}%</td>
                      <td className="p-2">{(r.gate_threshold_pct * 100).toFixed(2)}%</td>
                      <td className="p-2 font-bold">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${
                            isQuarantine
                              ? 'bg-rose-900/60 text-rose-200 border border-rose-700'
                              : r.action_channel === 'INSTANT_ALERT'
                              ? 'bg-emerald-900/60 text-emerald-200 border border-emerald-700'
                              : r.action_channel === 'INSTANT_DISTRIBUTION_WARNING'
                              ? 'bg-amber-900/60 text-amber-200 border border-amber-700'
                              : 'bg-slate-800 text-slate-300'
                          }`}
                        >
                          {r.action_channel}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Historical Alert Cooldowns */}
      {history?.active_alerts?.length > 0 && (
        <div className="mt-6 border-t border-slate-800 pt-4">
          <h3 className="text-xs font-bold uppercase text-slate-400 mb-2">
            Active Ticker Cooldowns (5-Day Anti-Spam Gate)
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 text-xs font-mono">
            {history.active_alerts.map((a: any) => (
              <div key={a.id} className="p-2 bg-slate-950 rounded border border-slate-800 flex justify-between items-center">
                <span className="font-bold text-sky-400">{a.ticker}</span>
                <span className="text-[11px] text-slate-400">
                  Cooldown: {new Date(a.cooldown_until).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
