import ScreenerTable from '@/components/ScreenerTable';
import { stockApi } from '@/lib/api';
import { Sparkles, Zap, ShieldCheck } from 'lucide-react';

export const metadata = {
  title: 'Philippine Equity Rankings Screener | StockPilot PH',
  description: 'Deterministic 3-layer scores and risk-adjusted Margin of Safety calculations for public equities on the Philippine Stock Exchange.',
};

export default async function ScreenerPage() {
  const stocks = await stockApi.getRankings('unified');

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      <div>
        <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400 mb-2">
          <Zap className="h-3.5 w-3.5 text-amber-400" />
          <span>Outcome as a Service • Quantitative Terminal</span>
        </div>
        <h1 className="text-3xl font-extrabold text-white tracking-tight sm:text-4xl">
          Philippine Equity Rankings Screener
        </h1>
        <p className="mt-2 text-sm text-slate-400 max-w-2xl leading-relaxed">
          Deterministic 3-layer audit (Financial Health, Improvement, Persistence) and intrinsic Margin of Safety valuations. Pay a flat fixed fee on demand, receive the full PDF dossier, and explore all 50+ scored companies with zero recurring monthly subscription lock-in.
        </p>
      </div>

      <ScreenerTable initialStocks={stocks} />
    </div>
  );
}
