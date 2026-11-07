'use client';

import React, { useEffect, useState } from 'react';
import { oaasApi, OaasRegimeData } from '@/lib/api';

export function MacroRegimeCard() {
  const [data, setData] = useState<OaasRegimeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadRegime() {
      try {
        setLoading(true);
        const res = await oaasApi.getRegime();
        setData(res);
      } catch (err: any) {
        console.warn('Failed to load macro regime:', err);
        setError('Unable to load live macro regime telemetry.');
      } finally {
        setLoading(false);
      }
    }
    loadRegime();
  }, []);

  if (loading) {
    return (
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 animate-pulse">
        <div className="h-4 bg-slate-800 rounded w-1/4 mb-4" />
        <div className="h-6 bg-slate-800 rounded w-1/2 mb-6" />
        <div className="h-20 bg-slate-800/40 rounded" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex items-center justify-between text-xs text-slate-400 mb-8">
        <span>Macro telemetry currently synchronizing.</span>
        <button
          onClick={() => {
            setLoading(true);
            setError(null);
            oaasApi.getRegime().then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false));
          }}
          className="text-sky-400 hover:underline font-medium"
        >
          Refresh Feed
        </button>
      </div>
    );
  }

  const { macro_shock_vector: m, top_allocations, is_pro_access, regime_title, quarantined_traps_count } = data;

  return (
    <div className="bg-gradient-to-br from-slate-900/90 to-slate-950 border border-slate-800 rounded-xl p-6 shadow-xl mb-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
            <span className="text-xs font-bold tracking-wider uppercase text-emerald-400">
              PSE Quantitative Outcome-as-a-Service (OaaS)
            </span>
          </div>
          <h2 className="text-xl font-bold text-white mt-1">
            Active Macro Regime: <span className="text-sky-400">{regime_title}</span>
          </h2>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
            PHP 10Y BVAL: <strong className="text-white">{(m.php_10y_bval_rate * 100).toFixed(2)}%</strong>
          </span>
          <span className="text-xs px-2.5 py-1 rounded bg-rose-950/60 text-rose-300 border border-rose-800/60">
            Quarantined Traps: <strong className="text-rose-200">{quarantined_traps_count}</strong>
          </span>
        </div>
      </div>

      {/* Macro Shocks Meter */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 my-4">
        <div className="bg-slate-950/60 p-2.5 rounded border border-slate-800/60 text-center">
          <div className="text-[11px] text-slate-400 uppercase font-semibold">BSP Policy Bias</div>
          <div className={`text-sm font-bold ${m.z_bsp_rate > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
            {m.z_bsp_rate > 0 ? `+${m.z_bsp_rate.toFixed(2)}σ` : `${m.z_bsp_rate.toFixed(2)}σ`}
          </div>
        </div>
        <div className="bg-slate-950/60 p-2.5 rounded border border-slate-800/60 text-center">
          <div className="text-[11px] text-slate-400 uppercase font-semibold">US 10Y Yield</div>
          <div className={`text-sm font-bold ${m.z_us10y_yield > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {m.z_us10y_yield > 0 ? `+${m.z_us10y_yield.toFixed(2)}σ` : `${m.z_us10y_yield.toFixed(2)}σ`}
          </div>
        </div>
        <div className="bg-slate-950/60 p-2.5 rounded border border-slate-800/60 text-center">
          <div className="text-[11px] text-slate-400 uppercase font-semibold">Brent Crude</div>
          <div className={`text-sm font-bold ${m.z_brent_crude > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {m.z_brent_crude > 0 ? `+${m.z_brent_crude.toFixed(2)}σ` : `${m.z_brent_crude.toFixed(2)}σ`}
          </div>
        </div>
        <div className="bg-slate-950/60 p-2.5 rounded border border-slate-800/60 text-center">
          <div className="text-[11px] text-slate-400 uppercase font-semibold">USD/PHP FX</div>
          <div className={`text-sm font-bold ${m.z_usd_php > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {m.z_usd_php > 0 ? `+${m.z_usd_php.toFixed(2)}σ` : `${m.z_usd_php.toFixed(2)}σ`}
          </div>
        </div>
        <div className="bg-slate-950/60 p-2.5 rounded border border-slate-800/60 text-center col-span-2 sm:col-span-1">
          <div className="text-[11px] text-slate-400 uppercase font-semibold">Foreign Flow (MSCI)</div>
          <div className={`text-sm font-bold ${m.z_msci_flow > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {m.z_msci_flow > 0 ? `+${m.z_msci_flow.toFixed(2)}σ` : `${m.z_msci_flow.toFixed(2)}σ`}
          </div>
        </div>
      </div>

      {/* Top Allocations Table */}
      <div className="mt-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Friction-Cleared Allocations (Size-Calibrated)
          </h3>
          {!is_pro_access && (
            <span className="text-xs text-amber-400 font-medium">
              🔒 Executable tickets & limit ladders locked to Pro/Institutional members
            </span>
          )}
        </div>

        {top_allocations.length === 0 ? (
          <div className="p-4 rounded bg-slate-950/40 text-center text-sm text-slate-400 border border-slate-800">
            Active defensive posture: zero tickers cleared the 2× Friction + 1.5σ volatility hurdle. Capital preserved in cash/defensive yield.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950 text-slate-400 text-xs uppercase font-semibold">
                <tr>
                  <th className="py-2.5 px-3">Ticker</th>
                  <th className="py-2.5 px-3">Ref Price</th>
                  <th className="py-2.5 px-3">Board Lot</th>
                  <th className="py-2.5 px-3">Friction</th>
                  <th className="py-2.5 px-3">Net Hurdle</th>
                  <th className="py-2.5 px-3">{is_pro_access ? 'Max Ticket / Sub' : 'Allocation'}</th>
                  <th className="py-2.5 px-3">{is_pro_access ? 'Resting Limit Ladder' : 'Execution Mode'}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                {top_allocations.map((a) => (
                  <tr key={a.ticker} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-sky-400">{a.ticker}</td>
                    <td className="py-2.5 px-3 text-slate-200">₱{a.price.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-slate-400">{a.board_lot.toLocaleString()} sh</td>
                    <td className="py-2.5 px-3 text-slate-400">{a.friction_bps.toFixed(0)} bps</td>
                    <td className="py-2.5 px-3 font-semibold text-emerald-400">
                      +{(a.net_hurdle_pct * 100).toFixed(2)}%
                    </td>
                    <td className="py-2.5 px-3">
                      {is_pro_access && a.executable_ticket_php ? (
                        <span className="font-bold text-white">
                          ₱{a.executable_ticket_php.toLocaleString('en-US', { maximumFractionDigits: 0 })}{' '}
                          <span className="text-xs text-slate-400">({a.executable_shares?.toLocaleString()} sh)</span>
                        </span>
                      ) : (
                        <span className="text-xs text-amber-400/80 font-mono">PRO ACCESS REQUIRED</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      {is_pro_access && a.limit_high ? (
                        <span className="text-xs font-mono bg-sky-950/80 text-sky-300 px-2 py-0.5 rounded border border-sky-800">
                          Limit Bid ≤ ₱{a.limit_high.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500 font-mono">Resting Limit Only</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
