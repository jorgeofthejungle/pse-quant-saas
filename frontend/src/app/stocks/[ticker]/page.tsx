import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeft,
  ShieldCheck,
  TrendingUp,
  Scale,
  Calendar,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { MOCK_STOCK_DETAILS, MOCK_RANKINGS } from '@/lib/mockData';
import { stockApi } from '@/lib/api';

export function generateStaticParams() {
  return MOCK_RANKINGS.map((stock) => ({
    ticker: stock.ticker,
  }));
}

interface StockDetailPageProps {
  params: Promise<{ ticker: string }>;
}

export default async function StockDetailPage({ params }: StockDetailPageProps) {
  const { ticker } = await params;
  const upperTicker = ticker.toUpperCase();

  // Look up detail from backend server with fallback
  const apiStock = await stockApi.getProfile(upperTicker);
  const stock = apiStock || MOCK_STOCK_DETAILS[upperTicker];

  if (!stock || !stock.ticker) {
    notFound();
  }

  const isPositiveMos = stock.mosPct !== null && stock.mosPct > 0;

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* ── Breadcrumb & Back ───────────────────────────── */}
      <div>
        <Link
          href="/screener"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Screener</span>
        </Link>
      </div>

      {/* ── Header Card ─────────────────────────────────── */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 backdrop-blur-md">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
                {stock.ticker}
              </h1>
              <span className="rounded-md bg-blue-500/10 border border-blue-500/20 px-2.5 py-0.5 text-xs font-semibold text-blue-400">
                {stock.scoringGroup}
              </span>
              <span className="rounded-md bg-slate-800 px-2.5 py-0.5 text-xs font-medium text-slate-300">
                Rank #{stock.rank}
              </span>
            </div>
            <p className="mt-1 text-slate-400 text-sm">{stock.name}</p>
          </div>

          <div className="flex items-center gap-6">
            <div className="text-right">
              <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">Current Price</span>
              <div className="text-2xl sm:text-3xl font-extrabold text-white">
                ₱{stock.currentPrice?.toFixed(2)}
              </div>
            </div>

            <div className="h-10 w-px bg-slate-800" />

            <div className="text-right">
              <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">Intrinsic Value</span>
              <div className="text-2xl sm:text-3xl font-extrabold text-blue-400">
                {stock.intrinsicValue ? `₱${stock.intrinsicValue.toFixed(2)}` : 'N/A'}
              </div>
            </div>

            <div className="h-10 w-px bg-slate-800" />

            <div className="text-right">
              <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">Margin of Safety</span>
              <div
                className={`text-2xl sm:text-3xl font-extrabold ${
                  isPositiveMos ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {stock.mosPct !== null ? `${stock.mosPct > 0 ? '+' : ''}${stock.mosPct.toFixed(1)}%` : 'N/A'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3-Layer Fundamental Score Breakdown ─────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Layer 1: Health */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">Layer 1</span>
            <span className="text-xs text-slate-400">Weight: {(stock.layers.health.weight * 100).toFixed(0)}%</span>
          </div>
          <h3 className="text-base font-bold text-white">Financial Health</h3>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">{stock.layers.health.score?.toFixed(1) ?? '—'}</span>
            <span className="text-xs text-slate-400">/ 100</span>
          </div>
          <div className="mt-3 h-2 w-full rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full"
              style={{ width: `${Math.min(100, stock.layers.health.score || 0)}%` }}
            />
          </div>
          <div className="mt-4 space-y-1.5 text-xs text-slate-400">
            {Object.entries(stock.layers.health.factors).map(([k, v]) => (
              <div key={k} className="flex justify-between py-0.5 border-b border-slate-800/40">
                <span className="capitalize">{k.replace('_', ' ')}</span>
                <span className="font-semibold text-slate-200">{v !== null ? `${v}/100` : 'N/A'}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Layer 2: Improvement */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-blue-400">Layer 2</span>
            <span className="text-xs text-slate-400">Weight: {(stock.layers.improvement.weight * 100).toFixed(0)}%</span>
          </div>
          <h3 className="text-base font-bold text-white">Improvement</h3>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">{stock.layers.improvement.score?.toFixed(1) ?? '—'}</span>
            <span className="text-xs text-slate-400">/ 100</span>
          </div>
          <div className="mt-3 h-2 w-full rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full"
              style={{ width: `${Math.min(100, stock.layers.improvement.score || 0)}%` }}
            />
          </div>
          <div className="mt-4 space-y-1.5 text-xs text-slate-400">
            {Object.entries(stock.layers.improvement.factors).map(([k, v]) => (
              <div key={k} className="flex justify-between py-0.5 border-b border-slate-800/40">
                <span className="capitalize">{k.replace('_', ' ')}</span>
                <span className="font-semibold text-slate-200">{v !== null ? `${v}/100` : 'N/A'}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Layer 3: Persistence */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-400">Layer 3</span>
            <span className="text-xs text-slate-400">Weight: {(stock.layers.persistence.weight * 100).toFixed(0)}%</span>
          </div>
          <h3 className="text-base font-bold text-white">Persistence</h3>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">{stock.layers.persistence.score?.toFixed(1) ?? '—'}</span>
            <span className="text-xs text-slate-400">/ 100</span>
          </div>
          <div className="mt-3 h-2 w-full rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-amber-500 rounded-full"
              style={{ width: `${Math.min(100, stock.layers.persistence.score || 0)}%` }}
            />
          </div>
          <div className="mt-4 space-y-1.5 text-xs text-slate-400">
            {Object.entries(stock.layers.persistence.factors).map(([k, v]) => (
              <div key={k} className="flex justify-between py-0.5 border-b border-slate-800/40">
                <span className="capitalize">{k.replace('_', ' ')}</span>
                <span className="font-semibold text-slate-200">{v !== null ? `${v}/100` : 'N/A'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Key Metrics & Valuation Breakdown ───────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Fundamental Ratios */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <h3 className="text-base font-bold text-white mb-4">Fundamental Ratios</h3>
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
            <div className="rounded-lg bg-slate-900/80 p-3 border border-slate-800">
              <dt className="text-xs text-slate-400">Return on Equity</dt>
              <dd className="text-lg font-bold text-white mt-1">{stock.roe?.toFixed(1)}%</dd>
            </div>
            <div className="rounded-lg bg-slate-900/80 p-3 border border-slate-800">
              <dt className="text-xs text-slate-400">P/E Ratio</dt>
              <dd className="text-lg font-bold text-white mt-1">{stock.pe ? `${stock.pe.toFixed(1)}x` : 'N/A'}</dd>
            </div>
            <div className="rounded-lg bg-slate-900/80 p-3 border border-slate-800">
              <dt className="text-xs text-slate-400">P/B Ratio</dt>
              <dd className="text-lg font-bold text-white mt-1">{stock.pb ? `${stock.pb.toFixed(2)}x` : 'N/A'}</dd>
            </div>
            <div className="rounded-lg bg-slate-900/80 p-3 border border-slate-800">
              <dt className="text-xs text-slate-400">Dividend Yield</dt>
              <dd className="text-lg font-bold text-white mt-1">{stock.dividendYield ? `${stock.dividendYield.toFixed(2)}%` : '—'}</dd>
            </div>
            <div className="rounded-lg bg-slate-900/80 p-3 border border-slate-800">
              <dt className="text-xs text-slate-400">Debt to Equity</dt>
              <dd className="text-lg font-bold text-white mt-1">{stock.deRatio ? `${stock.deRatio.toFixed(2)}x` : 'N/A'}</dd>
            </div>
            <div className="rounded-lg bg-slate-900/80 p-3 border border-slate-800">
              <dt className="text-xs text-slate-400">Required Return (r)</dt>
              <dd className="text-lg font-bold text-blue-400 mt-1">{(stock.requiredReturn * 100).toFixed(1)}%</dd>
            </div>
          </dl>
        </div>

        {/* Valuation Models */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <h3 className="text-base font-bold text-white mb-4">Intrinsic Value Components</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-slate-800">
              <div>
                <div className="text-sm font-semibold text-white">Dividend Discount Model (DDM)</div>
                <div className="text-xs text-slate-400">{stock.valuation.ddm.status}</div>
              </div>
              <div className="text-base font-bold text-slate-200">
                {stock.valuation.ddm.value ? `₱${stock.valuation.ddm.value.toFixed(2)}` : 'N/A'}
              </div>
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-slate-800">
              <div>
                <div className="text-sm font-semibold text-white">Normalised EPS x Target PE</div>
                <div className="text-xs text-slate-400">{stock.valuation.epsPe.status}</div>
              </div>
              <div className="text-base font-bold text-slate-200">
                {stock.valuation.epsPe.value ? `₱${stock.valuation.epsPe.value.toFixed(2)}` : 'N/A'}
              </div>
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-slate-800">
              <div>
                <div className="text-sm font-semibold text-white">Discounted Cash Flow (DCF)</div>
                <div className="text-xs text-slate-400">{stock.valuation.dcf.status}</div>
              </div>
              <div className="text-base font-bold text-slate-200">
                {stock.valuation.dcf.value ? `₱${stock.valuation.dcf.value.toFixed(2)}` : 'N/A'}
              </div>
            </div>

            {stock.valuation.conglomerateDiscountApplied && (
              <div className="flex items-center gap-2 text-xs text-amber-400/90 bg-amber-500/10 p-2.5 rounded-lg border border-amber-500/20">
                <Info className="h-4 w-4 shrink-0" />
                <span>Holding company 20% conglomerate discount applied to blended intrinsic value.</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Financial Statements History ─────────────────── */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
        <h3 className="text-base font-bold text-white mb-4">Historical Financials (PHP Millions)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-400">
              <tr>
                <th className="py-2.5 px-3">Fiscal Year</th>
                <th className="py-2.5 px-3">Revenue</th>
                <th className="py-2.5 px-3">Net Income</th>
                <th className="py-2.5 px-3">Equity</th>
                <th className="py-2.5 px-3">EPS (₱)</th>
                <th className="py-2.5 px-3">DPS (₱)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {stock.historicalFinancials.map((fin) => (
                <tr key={fin.year} className="hover:bg-slate-800/20">
                  <td className="py-2.5 px-3 font-semibold text-white">{fin.year}</td>
                  <td className="py-2.5 px-3">₱{fin.revenue.toLocaleString()} M</td>
                  <td className="py-2.5 px-3">₱{fin.netIncome.toLocaleString()} M</td>
                  <td className="py-2.5 px-3">₱{fin.equity.toLocaleString()} M</td>
                  <td className="py-2.5 px-3 font-medium text-slate-200">₱{fin.eps.toFixed(2)}</td>
                  <td className="py-2.5 px-3">{fin.dps !== null ? `₱${fin.dps.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
