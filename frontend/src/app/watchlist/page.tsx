'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Bookmark, Plus, Trash2, ArrowRight, ShieldCheck } from 'lucide-react';
import { MOCK_RANKINGS } from '@/lib/mockData';

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState([
    { ...MOCK_RANKINGS[0], targetMos: 25.0 },
    { ...MOCK_RANKINGS[1], targetMos: 20.0 },
  ]);
  const [newTicker, setNewTicker] = useState('');

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTicker) return;
    const found = MOCK_RANKINGS.find((s) => s.ticker.toLowerCase() === newTicker.toLowerCase());
    if (found && !watchlist.some((s) => s.ticker === found.ticker)) {
      setWatchlist([...watchlist, { ...found, targetMos: 20.0 }]);
      setNewTicker('');
    }
  };

  const handleRemove = (ticker: string) => {
    setWatchlist(watchlist.filter((s) => s.ticker !== ticker));
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400 mb-2">
            <Bookmark className="h-3.5 w-3.5" />
            <span>Member Portfolio</span>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">Your Watchlist</h1>
          <p className="mt-1 text-sm text-slate-400">
            Track your target Margin of Safety cushions and monitor fundamental quality shifts.
          </p>
        </div>

        <form onSubmit={handleAdd} className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Add ticker (e.g. BDO)..."
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            className="rounded-lg border border-slate-800 bg-slate-900 px-3.5 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            className="flex items-center gap-1 rounded-lg bg-blue-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-blue-500 transition-colors"
          >
            <Plus className="h-4 w-4" />
            <span>Add</span>
          </button>
        </form>
      </div>

      {watchlist.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="border-b border-slate-800 bg-slate-900/80 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3.5">Ticker</th>
                <th className="px-4 py-3.5">Sector</th>
                <th className="px-4 py-3.5">Score</th>
                <th className="px-4 py-3.5">Current Price</th>
                <th className="px-4 py-3.5">Intrinsic Value</th>
                <th className="px-4 py-3.5">Current MoS</th>
                <th className="px-4 py-3.5">Target MoS</th>
                <th className="px-4 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {watchlist.map((item) => {
                const isPositiveMos = item.mosPct !== null && item.mosPct > 0;
                return (
                  <tr key={item.ticker} className="hover:bg-slate-800/30">
                    <td className="px-4 py-3.5">
                      <Link href={`/stocks/${item.ticker}`} className="font-bold text-white hover:text-blue-400">
                        {item.ticker}
                      </Link>
                      <div className="text-xs text-slate-400">{item.name}</div>
                    </td>
                    <td className="px-4 py-3.5 text-xs text-slate-400">{item.scoringGroup}</td>
                    <td className="px-4 py-3.5 font-bold text-white">{item.score.toFixed(1)}</td>
                    <td className="px-4 py-3.5">₱{item.currentPrice.toFixed(2)}</td>
                    <td className="px-4 py-3.5 text-slate-400">
                      {item.intrinsicValue ? `₱${item.intrinsicValue.toFixed(2)}` : 'N/A'}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`font-bold ${isPositiveMos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {item.mosPct ? `${item.mosPct > 0 ? '+' : ''}${item.mosPct.toFixed(1)}%` : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-300 font-medium">
                      +{item.targetMos.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={() => handleRemove(item.ticker)}
                        className="text-slate-500 hover:text-rose-400 p-1 rounded transition-colors"
                        title="Remove from watchlist"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-800 p-12 text-center">
          <Bookmark className="mx-auto h-8 w-8 text-slate-600 mb-3" />
          <h3 className="text-base font-semibold text-white">Your watchlist is empty</h3>
          <p className="mt-1 text-sm text-slate-400 max-w-sm mx-auto">
            Pin high-quality stocks to monitor their Margin of Safety and valuation progress.
          </p>
          <div className="mt-6">
            <Link
              href="/screener"
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              <span>Explore Screener</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
