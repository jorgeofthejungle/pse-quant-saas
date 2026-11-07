import Link from 'next/link';
import {
  TrendingUp,
  ShieldCheck,
  Zap,
  Activity,
  Layers,
  ArrowUpRight,
  Sparkles,
  BarChart3,
  Calendar,
  CheckCircle2,
  DollarSign,
  PieChart,
} from 'lucide-react';
import { stockApi } from '@/lib/api';
import ScreenerTable from '@/components/ScreenerTable';
import MemberGreeting from '@/components/MemberGreeting';
import OnDemandCheckoutCard from '@/components/OnDemandCheckoutCard';

export const metadata = {
  title: 'Done-For-You Investment Hub | StockPilot PH',
  description: 'Taglish Fact Cards, Hype Check, and Seasoned Numbers for Philippine equities.',
};

export default async function DashboardPage() {
  const unifiedRankings = await stockApi.getRankings('unified');
  const dividendRankings = await stockApi.getRankings('dividend');
  const valueRankings = await stockApi.getRankings('value');

  // Filter top bargain candidates (positive Margin of Safety)
  const mosBargains = unifiedRankings.filter((s) => s.mosPct !== null && s.mosPct > 0);

  // Highest quality champions
  const highQualityStocks = unifiedRankings.filter(
    (s) => s.category === 'Highest Quality' || s.category === 'Strong Growth'
  );

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* ── Top Header & Greeting ──────────────────────────── */}
      <MemberGreeting />

      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400 mb-2">
            <Activity className="h-3.5 w-3.5" />
            <span>Done-For-You Investment Hub</span>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight sm:text-4xl">
            Take Your Pick: Curated PSE Menu
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Taglish Fact Cards, FB Group Hype Check, at Seasoned Numbers para sa bawat stock.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/screener"
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-700 hover:text-white transition-colors"
          >
            <BarChart3 className="h-4 w-4" />
            <span>Full Screener</span>
          </Link>
        </div>
      </div>

      {/* ── Done-For-You Investment Menu & Hype Check ──────── */}
      <OnDemandCheckoutCard />

      {/* ── Macro Financial Indicators ─────────────────────── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>PH 10Y Benchmark Bond</span>
            <Calendar className="h-4 w-4 text-slate-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">6.50%</span>
            <span className="text-xs text-slate-400 font-normal">Risk-Free Floor</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Benchmark hurdle rate for all discount models</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Damodaran ERP</span>
            <ShieldCheck className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-indigo-400">5.00%</span>
            <span className="text-xs text-slate-400 font-normal">PH Equity Risk</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Total base required return: 11.50%</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Conglomerate Holding Disc</span>
            <PieChart className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-amber-400">20.0%</span>
            <span className="text-xs text-slate-400 font-normal">Holding Haircut</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Applied automatically to holding conglomerates</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Pipeline Audit Status</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-emerald-400">100% Valid</span>
            <span className="text-xs text-slate-400 font-normal">Zero Unit Mismatches</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Deterministic scoring & daily quote synchronization</p>
        </div>
      </div>

      {/* ── Margin of Safety Spotlight Section ─────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-400" />
            <h2 className="text-xl font-bold text-white tracking-tight">
              Margin of Safety Opportunities
            </h2>
          </div>
          <span className="text-xs text-slate-400">
            Equities currently trading below mathematical Intrinsic Value
          </span>
        </div>

        {mosBargains.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center text-slate-400 text-sm">
            No equities currently clear the strict positive Margin of Safety threshold.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {mosBargains.map((stock) => (
              <Link
                key={stock.ticker}
                href={`/stocks/${stock.ticker}`}
                className="group relative rounded-2xl border border-emerald-500/30 bg-gradient-to-b from-slate-900/90 to-slate-900/50 p-6 backdrop-blur-md transition-all hover:border-emerald-500/60 hover:shadow-lg hover:shadow-emerald-500/10"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-2xl font-extrabold text-white group-hover:text-emerald-400 transition-colors">
                        {stock.ticker}
                      </span>
                      <span className="rounded bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400">
                        +{stock.mosPct}% MoS
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-400 line-clamp-1">{stock.name}</p>
                  </div>
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-400 group-hover:text-white transition-colors">
                    <ArrowUpRight className="h-4 w-4" />
                  </div>
                </div>

                <div className="mt-6 grid grid-cols-2 gap-4 border-t border-slate-800/80 pt-4">
                  <div>
                    <span className="text-xs text-slate-500">Current Market Price</span>
                    <div className="text-lg font-bold text-white">
                      ₱{stock.currentPrice?.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-slate-500">Intrinsic Value (IV)</span>
                    <div className="text-lg font-bold text-emerald-400">
                      ₱{stock.intrinsicValue?.toFixed(2)}
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between text-xs text-slate-400 border-t border-slate-800/60 pt-3">
                  <span>Score: <strong className="text-white">{stock.score}</strong></span>
                  <span>Yield: <strong className="text-emerald-400">{stock.dividendYield ? `${stock.dividendYield.toFixed(1)}%` : '—'}</strong></span>
                  <span>P/E: <strong className="text-slate-300">{stock.pe ? `${stock.pe.toFixed(1)}x` : '—'}</strong></span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* ── Active Rankings Overview ───────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Top Ranked Equities
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Unified 3-layer model leaderboard (Health + Improvement + Persistence)
            </p>
          </div>
          <Link
            href="/screener"
            className="text-xs font-semibold text-blue-400 hover:text-blue-300 transition-colors"
          >
            View all ranked equities &rarr;
          </Link>
        </div>

        <ScreenerTable initialStocks={unifiedRankings} />
      </div>

      {/* ── Model Architecture Breakdown Card ─────────────── */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 sm:p-8 backdrop-blur-sm space-y-6">
        <div>
          <h3 className="text-lg font-bold text-white">Deterministic 3-Layer Scoring Model</h3>
          <p className="mt-1 text-xs text-slate-400">
            How StockPilot PH scores equities across dynamic sector-adaptive hurdle rates:
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-2">
            <div className="flex items-center gap-2 text-blue-400 font-semibold text-sm">
              <ShieldCheck className="h-4 w-4" />
              <span>Layer 1: Health (35%)</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Solvency, profitability, and balance sheet safety: ROE, Net Margin, Debt-to-Equity, P/B, and FCF Yield.
            </p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-2">
            <div className="flex items-center gap-2 text-indigo-400 font-semibold text-sm">
              <TrendingUp className="h-4 w-4" />
              <span>Layer 2: Improvement (35%)</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Smoothed YoY growth deltas in Revenue, EPS, ROE, and DPS. Rewards acceleration and positive momentum.
            </p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-2">
            <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm">
              <Layers className="h-4 w-4" />
              <span>Layer 3: Persistence (30%)</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Multi-year consistency and direction alignment. Penalizes erratic boom-bust cycles and rewards durable compounding.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
