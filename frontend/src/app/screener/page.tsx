import ScreenerTable from '@/components/ScreenerTable';
import { stockApi } from '@/lib/api';
import { Sparkles } from 'lucide-react';

export default async function ScreenerPage() {
  const stocks = await stockApi.getRankings('unified');

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
      <div className="mb-8">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400 mb-2">
          <Sparkles className="h-3.5 w-3.5" />
          <span>Interactive Universe</span>
        </div>
        <h1 className="text-3xl font-extrabold text-white tracking-tight">
          Philippine Equity Rankings Screener
        </h1>
        <p className="mt-2 text-sm text-slate-400 max-w-2xl">
          Deterministic 3-layer scores (Health, Improvement, Persistence) and risk-adjusted Margin of Safety calculations for public equities on the Philippine Stock Exchange.
        </p>
      </div>

      <ScreenerTable initialStocks={stocks} />
    </div>
  );
}
