'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { Bookmark, Plus, Trash2, ArrowRight, ShieldCheck, Bell, Sparkles } from 'lucide-react';
import { customerApi, stockApi, WatchlistItem } from '@/lib/api';
import { MOCK_RANKINGS } from '@/lib/mockData';

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<any[]>([
    {
      ticker: 'AREIT',
      name: 'AREIT, Inc.',
      sector: 'Property',
      score: 73.0,
      currentPrice: 36.50,
      intrinsicValue: 46.84,
      mosPct: 22.1,
      targetMos: 20.0,
      isTriggered: true,
    },
    {
      ticker: 'DMC',
      name: 'DMCI Holdings, Inc.',
      sector: 'Holding Firms',
      score: 68.5,
      currentPrice: 12.40,
      intrinsicValue: 15.20,
      mosPct: 18.4,
      targetMos: 25.0,
      isTriggered: false,
    },
  ]);
  const [newTicker, setNewTicker] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Attempt to load customer 1 watchlist from backend server
    customerApi.getWatchlist(1).then((items) => {
      if (items && items.length > 0) {
        setWatchlist(
          items.map((i) => ({
            ticker: i.ticker,
            name: i.name,
            sector: i.sector,
            score: 73.0,
            currentPrice: i.current_price || 0,
            intrinsicValue: i.intrinsic_value,
            mosPct: i.current_mos_pct,
            targetMos: i.target_mos_pct,
            isTriggered: i.is_triggered,
            notes: i.notes,
          }))
        );
      }
    });
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTicker.trim()) return;
    const sym = newTicker.trim().toUpperCase();
    if (watchlist.some((s) => s.ticker === sym)) {
      setNewTicker('');
      return;
    }

    setLoading(true);
    // Send to backend server
    await customerApi.addToWatchlist(1, sym, 20.0);

    // Refresh profile from stockApi
    const profile = await stockApi.getProfile(sym);
    if (profile) {
      setWatchlist([
        ...watchlist,
        {
          ticker: profile.ticker,
          name: profile.name,
          sector: profile.sector,
          score: profile.score || 70.0,
          currentPrice: profile.currentPrice || 0,
          intrinsicValue: profile.intrinsicValue,
          mosPct: profile.mosPct,
          targetMos: 20.0,
          isTriggered: profile.mosPct !== null && profile.mosPct >= 20.0,
        },
      ]);
    } else {
      const mock = MOCK_RANKINGS.find((s) => s.ticker === sym);
      if (mock) {
        setWatchlist([...watchlist, { ...mock, targetMos: 20.0, isTriggered: false }]);
      }
    }
    setNewTicker('');
    setLoading(false);
  };

  const handleRemove = async (ticker: string) => {
    setWatchlist(watchlist.filter((s) => s.ticker !== ticker));
    await customerApi.removeFromWatchlist(1, ticker);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400 mb-2">
            <Bookmark className="h-3.5 w-3.5" />
            <span>Customer Portfolio Tracker</span>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">Personal Watchlist</h1>
          <p className="mt-1 text-sm text-slate-400">
            Set custom Margin of Safety target cushions and receive automated alert notifications.
          </p>
        </div>

        <form onSubmit={handleAdd} className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Add ticker (e.g. ICT, BDO)..."
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            disabled={loading}
            className="rounded-lg border border-slate-800 bg-slate-900 px-3.5 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-1 rounded-lg bg-blue-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
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
                <th className="px-4 py-3.5">Alert Status</th>
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
                    <td className="px-4 py-3.5 text-xs text-slate-400">{item.sector}</td>
                    <td className="px-4 py-3.5 font-bold text-white">
                      {typeof item.score === 'number' ? item.score.toFixed(1) : item.score}
                    </td>
                    <td className="px-4 py-3.5">₱{item.currentPrice?.toFixed(2)}</td>
                    <td className="px-4 py-3.5 text-slate-400">
                      {item.intrinsicValue ? `₱${item.intrinsicValue.toFixed(2)}` : 'N/A'}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`font-bold ${isPositiveMos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {item.mosPct ? `${item.mosPct > 0 ? '+' : ''}${item.mosPct.toFixed(1)}%` : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-300 font-medium">
                      +{item.targetMos?.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3.5">
                      {item.isTriggered ? (
                        <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400">
                          <Bell className="h-3 w-3" />
                          <span>Target Reached</span>
                        </span>
                      ) : (
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                          Monitoring
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          href={`/stocks/${item.ticker}`}
                          className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
                          title="View Profile"
                        >
                          <ArrowRight className="h-4 w-4" />
                        </Link>
                        <button
                          onClick={() => handleRemove(item.ticker)}
                          className="rounded p-1.5 text-slate-500 hover:bg-rose-500/10 hover:text-rose-400 transition-colors"
                          title="Remove from Watchlist"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center">
          <Bookmark className="mx-auto h-10 w-10 text-slate-600 mb-3" />
          <h3 className="text-base font-semibold text-white">Your watchlist is empty</h3>
          <p className="mt-1 text-sm text-slate-400 max-w-sm mx-auto">
            Use the input above or explore the Screener to bookmark stocks with your desired Margin of Safety cushion.
          </p>
          <div className="mt-6">
            <Link
              href="/screener"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 transition-colors"
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
