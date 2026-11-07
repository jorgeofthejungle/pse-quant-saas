'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ShieldAlert,
  Play,
  RefreshCw,
  Mail,
  Bell,
  Users,
  DollarSign,
  Activity,
  Layers,
  Database,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Sliders,
  Sparkles,
} from 'lucide-react';
import { adminApi, AdminMetrics, PipelineRunLog } from '@/lib/api';
import { CausalEngineConsole } from '@/components/CausalEngineConsole';

export default function AdminDashboardPage() {
  const router = useRouter();
  const [metrics, setMetrics] = useState<AdminMetrics>({
    total_customers: 1,
    paid_subscribers: 1,
    free_members: 0,
    mrr_php: 499.0,
    active_watchlists: 1,
    total_emails_delivered: 0,
  });

  const [runs, setRuns] = useState<PipelineRunLog[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Manual override form state
  const [overrideTicker, setOverrideTicker] = useState('AREIT');
  const [overrideYear, setOverrideYear] = useState(2024);
  const [overrideRevenue, setOverrideRevenue] = useState('');
  const [overrideNetIncome, setOverrideNetIncome] = useState('');
  const [overrideEquity, setOverrideEquity] = useState('');
  const [overrideEps, setOverrideEps] = useState('');

  const loadData = async () => {
    try {
      const [m, r, c] = await Promise.all([
        adminApi.getMetrics(),
        adminApi.getPipelineRuns(10),
        adminApi.listCustomers(0, 20),
      ]);
      if (m) setMetrics(m);
      if (r) setRuns(r);
      if (c) setCustomers(c);
    } catch (err: any) {
      if (err?.message?.includes('401') || err?.message?.includes('403')) {
        localStorage.removeItem('stockpilot_admin_token');
        router.push('/admin/login');
      }
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAction = async (actionName: string, actionFn: () => Promise<any>) => {
    setLoadingAction(actionName);
    setStatusMessage(null);
    try {
      const res = await actionFn();
      setStatusMessage({
        type: 'success',
        text: `Action "${actionName}" completed successfully: ${JSON.stringify(res.summary || res.status || 'OK')}`,
      });
      await loadData();
    } catch (err: any) {
      setStatusMessage({
        type: 'error',
        text: `Action "${actionName}" failed: ${err.message || 'Unknown error'}`,
      });
    } finally {
      setLoadingAction(null);
    }
  };

  const handleOverrideSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoadingAction('override');
    setStatusMessage(null);
    try {
      const payload: any = {};
      if (overrideRevenue) payload.revenue = parseFloat(overrideRevenue);
      if (overrideNetIncome) payload.net_income = parseFloat(overrideNetIncome);
      if (overrideEquity) payload.equity = parseFloat(overrideEquity);
      if (overrideEps) payload.eps = parseFloat(overrideEps);

      const res = await adminApi.overrideFinancials(overrideTicker, overrideYear, payload);
      setStatusMessage({
        type: 'success',
        text: `Successfully updated financial statement for ${overrideTicker} FY${overrideYear}`,
      });
      setOverrideRevenue('');
      setOverrideNetIncome('');
      setOverrideEquity('');
      setOverrideEps('');
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: `Override failed: ${err.message}` });
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* ── Top Header & Server Connection ─────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-0.5 text-xs font-semibold text-rose-400 mb-2">
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>Admin Operator Console</span>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">Server Command Center</h1>
          <p className="mt-1 text-sm text-slate-400">
            Direct real-time controls, quantitative pipeline triggers, customer intelligence, and financial overrides.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3.5 py-1.5 text-xs text-slate-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>FastAPI Server: <strong>127.0.0.1:8000</strong></span>
          </div>
        </div>
      </div>

      {/* ── Status Notification Banner ─────────────────────── */}
      {statusMessage && (
        <div
          className={`rounded-xl p-4 border text-xs font-medium flex items-center justify-between ${
            statusMessage.type === 'success'
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
              : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
          }`}
        >
          <span>{statusMessage.text}</span>
          <button onClick={() => setStatusMessage(null)} className="underline ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* ── SaaS Business Telemetry Grid ───────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Total Customers</span>
            <Users className="h-4 w-4 text-blue-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-white">{metrics.total_customers}</div>
          <p className="mt-1 text-xs text-slate-500">
            {metrics.paid_subscribers} paid • {metrics.free_members} free
          </p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Estimated MRR</span>
            <DollarSign className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-emerald-400">
            ₱{metrics.mrr_php.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
          <p className="mt-1 text-xs text-slate-500">Monthly Recurring Revenue</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Active Watchlists</span>
            <Bell className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-indigo-400">{metrics.active_watchlists}</div>
          <p className="mt-1 text-xs text-slate-500">Target MoS alert rules monitored</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Research Reports Delivered</span>
            <Mail className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-amber-400">{metrics.total_emails_delivered}</div>
          <p className="mt-1 text-xs text-slate-500">Weekly PDF digests via Resend API</p>
        </div>
      </div>

      {/* ── Causal Alert Engine & Macro Triage Controller ──── */}
      <CausalEngineConsole />

      {/* ── Direct Pipeline Control Operations ─────────────── */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 sm:p-8 backdrop-blur-sm space-y-6">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">Direct Pipeline Controls</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Execute batch collection, re-scoring, alert evaluations, and subscriber email blasts.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <button
            onClick={() => handleAction('Full ETL Sync', () => adminApi.triggerFullPipeline())}
            disabled={loadingAction !== null}
            className="flex flex-col items-start p-4 rounded-xl border border-blue-500/20 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 transition-all text-left disabled:opacity-50"
          >
            <div className="flex items-center justify-between w-full mb-2">
              <Play className="h-5 w-5" />
              {loadingAction === 'Full ETL Sync' && <RefreshCw className="h-4 w-4 animate-spin" />}
            </div>
            <span className="font-bold text-white text-sm">Run Full Scrape & Score</span>
            <span className="text-xs text-slate-400 mt-1">Scrapes PSE Edge directory, quotes, financials and recomputes all scores.</span>
          </button>

          <button
            onClick={() => handleAction('Quote Refresh', () => adminApi.triggerQuoteScrape())}
            disabled={loadingAction !== null}
            className="flex flex-col items-start p-4 rounded-xl border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-200 transition-all text-left disabled:opacity-50"
          >
            <div className="flex items-center justify-between w-full mb-2">
              <RefreshCw className="h-5 w-5 text-indigo-400" />
              {loadingAction === 'Quote Refresh' && <RefreshCw className="h-4 w-4 animate-spin text-indigo-400" />}
            </div>
            <span className="font-bold text-white text-sm">Refresh Daily Quotes</span>
            <span className="text-xs text-slate-400 mt-1">Updates market close prices and dividend declarations without full scrape.</span>
          </button>

          <button
            onClick={() => handleAction('Recompute Scores', () => adminApi.triggerRecomputeScores())}
            disabled={loadingAction !== null}
            className="flex flex-col items-start p-4 rounded-xl border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-200 transition-all text-left disabled:opacity-50"
          >
            <div className="flex items-center justify-between w-full mb-2">
              <Layers className="h-5 w-5 text-emerald-400" />
              {loadingAction === 'Recompute Scores' && <RefreshCw className="h-4 w-4 animate-spin text-emerald-400" />}
            </div>
            <span className="font-bold text-white text-sm">Re-Score All Equities</span>
            <span className="text-xs text-slate-400 mt-1">Recomputes 3-layer scores, dynamic percentiles, and Margin of Safety.</span>
          </button>

          <button
            onClick={() => handleAction('Send Research Digest', () => adminApi.triggerEmailDigest())}
            disabled={loadingAction !== null}
            className="flex flex-col items-start p-4 rounded-xl border border-amber-500/20 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 transition-all text-left disabled:opacity-50"
          >
            <div className="flex items-center justify-between w-full mb-2">
              <Mail className="h-5 w-5" />
              {loadingAction === 'Send Research Digest' && <RefreshCw className="h-4 w-4 animate-spin" />}
            </div>
            <span className="font-bold text-white text-sm">Dispatch Weekly Report</span>
            <span className="text-xs text-slate-400 mt-1">Generates executive A4 PDF and emails it to all active subscribers.</span>
          </button>
        </div>
      </div>

      {/* ── Two-Column Operational Split: Customers & Overrides ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Customer Intelligence Table */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white text-lg">Customer Management</h3>
            <span className="text-xs text-slate-400">{customers.length} registered</span>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="border-b border-slate-800 bg-slate-800/60 uppercase text-slate-400">
                <tr>
                  <th className="px-3.5 py-2.5">Email</th>
                  <th className="px-3.5 py-2.5">Tier</th>
                  <th className="px-3.5 py-2.5">Plan</th>
                  <th className="px-3.5 py-2.5">Watchlist</th>
                  <th className="px-3.5 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {customers.length > 0 ? (
                  customers.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-800/40">
                      <td className="px-3.5 py-2.5 font-medium text-white">{c.email}</td>
                      <td className="px-3.5 py-2.5">
                        <span
                          className={`px-1.5 py-0.5 rounded font-semibold ${
                            c.tier === 'paid'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {c.tier}
                        </span>
                      </td>
                      <td className="px-3.5 py-2.5 capitalize">{c.plan}</td>
                      <td className="px-3.5 py-2.5">{c.watchlist_count} items</td>
                      <td className="px-3.5 py-2.5 text-emerald-400">{c.status}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="text-center py-6 text-slate-500">
                      No customer accounts registered yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Manual Financial Statement Override Form */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          <div>
            <h3 className="font-bold text-white text-lg">Financial Statement Manual Override</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Admin capability to update or correct line items if PSE Edge reports are delayed or restated.
            </p>
          </div>

          <form onSubmit={handleOverrideSubmit} className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 font-medium">Ticker Symbol</label>
                <input
                  type="text"
                  value={overrideTicker}
                  onChange={(e) => setOverrideTicker(e.target.value)}
                  className="w-full mt-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-white outline-none focus:border-blue-500 font-semibold"
                />
              </div>
              <div>
                <label className="text-slate-400 font-medium">Fiscal Year</label>
                <input
                  type="number"
                  value={overrideYear}
                  onChange={(e) => setOverrideYear(parseInt(e.target.value))}
                  className="w-full mt-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-white outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 font-medium">Gross Revenue (PHP Millions)</label>
                <input
                  type="number"
                  step="any"
                  placeholder="e.g. 125000"
                  value={overrideRevenue}
                  onChange={(e) => setOverrideRevenue(e.target.value)}
                  className="w-full mt-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-white outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-slate-400 font-medium">Net Income (PHP Millions)</label>
                <input
                  type="number"
                  step="any"
                  placeholder="e.g. 25000"
                  value={overrideNetIncome}
                  onChange={(e) => setOverrideNetIncome(e.target.value)}
                  className="w-full mt-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-white outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 font-medium">Stockholders' Equity (PHP Millions)</label>
                <input
                  type="number"
                  step="any"
                  placeholder="e.g. 85000"
                  value={overrideEquity}
                  onChange={(e) => setOverrideEquity(e.target.value)}
                  className="w-full mt-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-white outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-slate-400 font-medium">Basic EPS (PHP)</label>
                <input
                  type="number"
                  step="any"
                  placeholder="e.g. 2.95"
                  value={overrideEps}
                  onChange={(e) => setOverrideEps(e.target.value)}
                  className="w-full mt-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-white outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loadingAction === 'override'}
              className="w-full mt-2 rounded-lg bg-blue-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
            >
              {loadingAction === 'override' ? 'Applying Override...' : 'Commit Financial Override to Server'}
            </button>
          </form>
        </div>
      </div>

      {/* ── Pipeline Execution Audit Log ───────────────────── */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-white text-lg">Pipeline Execution History</h3>
          <span className="text-xs text-slate-400">Audit logs & canaries</span>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="border-b border-slate-800 bg-slate-800/60 uppercase text-slate-400">
              <tr>
                <th className="px-3.5 py-2.5">ID</th>
                <th className="px-3.5 py-2.5">Run Type</th>
                <th className="px-3.5 py-2.5">Status</th>
                <th className="px-3.5 py-2.5">Summary / Results</th>
                <th className="px-3.5 py-2.5">Started At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {runs.length > 0 ? (
                runs.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-800/40">
                    <td className="px-3.5 py-2.5 font-bold text-slate-400">#{r.id}</td>
                    <td className="px-3.5 py-2.5 font-semibold text-white">{r.run_type}</td>
                    <td className="px-3.5 py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          r.status === 'completed'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                        }`}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-3.5 py-2.5 text-slate-400 font-mono">
                      {JSON.stringify(r.summary || r.error_message || {})}
                    </td>
                    <td className="px-3.5 py-2.5 text-slate-500">{new Date(r.started_at).toLocaleString()}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="text-center py-6 text-slate-500">
                    No pipeline runs recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
