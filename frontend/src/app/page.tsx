'use client';

import Link from 'next/link';
import {
  TrendingUp,
  ShieldCheck,
  Zap,
  Clock,
  Compass,
  ArrowRight,
  Mail,
  CheckCircle2,
  FileText,
} from 'lucide-react';
import ScreenerTable from '@/components/ScreenerTable';
import { MOCK_RANKINGS } from '@/lib/mockData';

export default function HomePage() {
  return (
    <div className="flex flex-col gap-20 pb-20">
      {/* ── Hero Section ───────────────────────────────────── */}
      <section className="relative overflow-hidden pt-20 pb-12 sm:pt-28">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(37,99,235,0.15),rgba(255,255,255,0))]" />
        
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-500/10 px-3.5 py-1 text-xs font-semibold text-blue-400 mb-6">
            <span className="flex h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
            StockPilot PH • 2026 Rebuild Architecture
          </div>

          <h1 className="mx-auto max-w-4xl text-4xl font-extrabold tracking-tight text-white sm:text-6xl sm:leading-tight">
            Deterministic Philippine Equity Rankings &{' '}
            <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-amber-300 bg-clip-text text-transparent">
              Margin of Safety
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-400 leading-relaxed">
            Every PSE company audited across financial health, fundamental improvement, and persistence. 
            Receive professional weekly A4 research reports and pre-market morning briefings in your inbox.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/screener"
              className="flex w-full sm:w-auto items-center justify-center gap-2 rounded-xl bg-blue-600 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 transition-all hover:bg-blue-500"
            >
              <Compass className="h-4 w-4" />
              <span>Explore Rankings Screener</span>
              <ArrowRight className="h-4 w-4" />
            </Link>

            <a
              href="#subscribe"
              className="flex w-full sm:w-auto items-center justify-center gap-2 rounded-xl border border-slate-800 bg-slate-900/60 px-6 py-3.5 text-sm font-semibold text-slate-300 transition-all hover:bg-slate-800 hover:text-white"
            >
              <Mail className="h-4 w-4" />
              <span>Get Weekly PDF Reports</span>
            </a>
          </div>
        </div>
      </section>

      {/* ── 3-Layer Fundamental Model Explainer ───────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-xs font-bold uppercase tracking-wider text-blue-400">Quantitative Framework</h2>
          <p className="mt-2 text-3xl font-extrabold tracking-tight text-white">
            The 3-Layer Fundamental Scoring Engine
          </p>
          <p className="mt-3 text-slate-400 text-sm max-w-xl mx-auto">
            Zero randomness, zero AI guesswork. A pure mathematical framework calibrated specifically for Philippine market realities.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 mb-4 border border-emerald-500/20">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Layer 1: Financial Health</h3>
            <span className="text-xs font-semibold text-emerald-400">30% – 35% Weight</span>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Audits solvency, balance sheet leverage, ROE, net margins, and cash flow generation. Sector-aware adjustments ensure banks aren&apos;t penalized for debt, and REITs score on FFO yield.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400 mb-4 border border-blue-500/20">
              <Zap className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Layer 2: Improvement</h3>
            <span className="text-xs font-semibold text-blue-400">25% – 30% Weight</span>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Evaluates recency-weighted YoY deltas (50/30/20) across revenue, EPS, and ROE. Rewards accelerating operational performance with fundamental momentum bonuses.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 mb-4 border border-amber-500/20">
              <Clock className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Layer 3: Persistence</h3>
            <span className="text-xs font-semibold text-amber-400">35% – 45% Weight</span>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Measures direction alignment, magnitude, and consecutive annual growth streaks. Separates reliable compounders from volatile one-hit wonders.
            </p>
          </div>
        </div>
      </section>

      {/* ── Live Leaderboard Preview ──────────────────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-blue-400">Market Preview</h2>
            <p className="mt-1 text-2xl font-extrabold text-white">Top Qualifying Equities</p>
            <p className="text-sm text-slate-400 mt-1">
              Live sample of publicly traded equities ranked above the dynamic statistical threshold.
            </p>
          </div>
          <Link
            href="/screener"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-400 hover:text-blue-300"
          >
            <span>View Full Universe</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        <ScreenerTable initialStocks={MOCK_RANKINGS} />
      </section>

      {/* ── Email Subscription Section ────────────────────── */}
      <section id="subscribe" className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-b from-slate-900/90 to-slate-950 p-8 sm:p-12 text-center shadow-2xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/20 bg-amber-500/10 px-3.5 py-1 text-xs font-semibold text-amber-400 mb-4">
            <Mail className="h-3.5 w-3.5" />
            <span>Email Research Service</span>
          </div>

          <h2 className="text-3xl font-extrabold text-white sm:text-4xl">
            Get the Weekly StockPilot PH Research PDF
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-sm text-slate-400 leading-relaxed">
            Delivered directly to your inbox every Sunday evening. Includes comprehensive rankings tables, individual stock breakdowns, and Margin of Safety reference figures.
          </p>

          <form className="mx-auto mt-8 flex max-w-md flex-col gap-3 sm:flex-row" onSubmit={(e) => e.preventDefault()}>
            <input
              type="email"
              placeholder="Enter your email address"
              required
              className="flex-1 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
            <button
              type="submit"
              className="rounded-xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white shadow-md shadow-blue-500/20 transition-all hover:bg-blue-500"
            >
              Subscribe
            </button>
          </form>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-6 text-xs text-slate-400">
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span>Full A4 PDF Report</span>
            </div>
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span>Pre-market alerts</span>
            </div>
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span>No spam • Unsubscribe anytime</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
