'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { Bookmark, Plus, Trash2, ArrowRight, ShieldCheck, Bell, Sparkles, LogIn, CheckCircle2, AlertCircle } from 'lucide-react';
import { watchlistApi, stockApi, WatchlistItem } from '@/lib/api';
import { MOCK_RANKINGS } from '@/lib/mockData';

interface WatchlistDisplayItem {
  ticker: string;
  name: string;
  sector: string;
  score: number;
  currentPrice: number | null;
  intrinsicValue: number | null;
  mosPct: number | null;
  targetMos: number;
  isTriggered: boolean;
  notes?: string;
}

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<WatchlistDisplayItem[]>([]);
  const [newTicker, setNewTicker] = useState('');
  const [newTargetMos, setNewTargetMos] = useState<number>(20.0);
  const [newNotes, setNewNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Check login state and fetch initial watchlist
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('stockpilot_member_token') : null;
    const storedUser = typeof window !== 'undefined' ? localStorage.getItem('stockpilot_member_user') : null;

    if (token) {
      setIsLoggedIn(true);
      if (storedUser) {
        try {
          const parsed = JSON.parse(storedUser);
          setUserEmail(parsed.email || null);
        } catch (e) {
          // ignore json parse error
        }
      }

      setLoading(true);
      watchlistApi
        .getWatchlist()
        .then((items) => {
          if (items && items.length > 0) {
            setWatchlist(
              items.map((i) => ({
                ticker: i.ticker,
                name: i.name,
                sector: i.sector,
                score: 72.0, // fallback score if not embedded
                currentPrice: i.current_price,
                intrinsicValue: i.intrinsic_value,
                mosPct: i.current_mos_pct,
                targetMos: i.target_mos_pct,
                isTriggered: i.is_triggered,
                notes: i.notes,
              }))
            );
          } else {
            setWatchlist([]);
          }
        })
        .finally(() => setLoading(false));
    } else {
      setIsLoggedIn(false);
      // Fallback guest demonstration items
      setWatchlist([
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
          notes: 'High-yield REIT asset',
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
          notes: 'Dividend powerhouse holding firm',
        },
      ]);
    }
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTicker.trim()) return;
    const sym = newTicker.trim().toUpperCase();

    if (watchlist.some((s) => s.ticker === sym)) {
      setStatusMessage({ text: `${sym} is already in your watchlist.`, type: 'error' });
      return;
    }

    setLoading(true);
    setStatusMessage(null);

    if (isLoggedIn) {
      const ok = await watchlistApi.addToWatchlist(sym, newTargetMos, newNotes.trim() || undefined);
      if (!ok) {
        setStatusMessage({ text: `Failed to add ${sym}. Ensure the ticker symbol is valid.`, type: 'error' });
        setLoading(false);
        return;
      }
    }

    // Enrich with live profile if available
    const profile = await stockApi.getProfile(sym);
    if (profile) {
      const mos = profile.mosPct;
      const triggered = mos !== null && mos >= newTargetMos;
      const newItem: WatchlistDisplayItem = {
        ticker: profile.ticker,
        name: profile.name,
        sector: profile.sector,
        score: profile.score || 70.0,
        currentPrice: profile.currentPrice || null,
        intrinsicValue: profile.intrinsicValue,
        mosPct: profile.mosPct,
        targetMos: newTargetMos,
        isTriggered: triggered,
        notes: newNotes.trim() || undefined,
      };
      setWatchlist((prev) => [newItem, ...prev]);
    } else {
      const mock = MOCK_RANKINGS.find((s) => s.ticker === sym);
      const newItem: WatchlistDisplayItem = {
        ticker: sym,
        name: mock ? mock.name : sym,
        sector: mock ? mock.sector : 'General',
        score: mock ? mock.score : 70.0,
        currentPrice: mock ? mock.currentPrice : null,
        intrinsicValue: mock ? mock.intrinsicValue : null,
        mosPct: mock ? mock.mosPct : null,
        targetMos: newTargetMos,
        isTriggered: mock && mock.mosPct !== null ? mock.mosPct >= newTargetMos : false,
        notes: newNotes.trim() || undefined,
      };
      setWatchlist((prev) => [newItem, ...prev]);
    }

    setStatusMessage({ text: `Added ${sym} to watchlist.`, type: 'success' });
    setNewTicker('');
    setNewNotes('');
    setLoading(false);
    setTimeout(() => setStatusMessage(null), 4000);
  };

  const handleRemove = async (ticker: string) => {
    const sym = ticker.toUpperCase();
    setWatchlist((prev) => prev.filter((s) => s.ticker !== sym));
    if (isLoggedIn) {
      await watchlistApi.removeFromWatchlist(sym);
    }
    setStatusMessage({ text: `Removed ${sym} from watchlist.`, type: 'success' });
    setTimeout(() => setStatusMessage(null), 3000);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400 mb-2">
            <Bookmark className="h-3.5 w-3.5" />
            <span>Member Portfolio Tracker</span>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">Personal Watchlist</h1>
          <p className="mt-1 text-sm text-slate-400">
            Set custom Margin of Safety target cushions and receive automated alert notifications.
          </p>
        </div>

        {/* Guest Warning / Logged-in Indicator */}
        {isLoggedIn ? (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3.5 py-2 text-xs font-medium text-emerald-400">
            <ShieldCheck className="h-4 w-4" />
            <span>Connected: <strong>{userEmail}</strong> (Cloud Synced)</span>
          </div>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3.5 py-2 text-xs font-semibold text-amber-300 hover:bg-amber-500/20 transition-colors"
          >
            <LogIn className="h-4 w-4" />
            <span>Guest Mode — Sign in to sync across devices</span>
          </Link>
        )}
      </div>

      {/* Add Stock Card */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <form onSubmit={handleAdd} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="flex-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">PSE Ticker</label>
            <input
              type="text"
              placeholder="e.g. AREIT, DMC, ICT, BDO"
              value={newTicker}
              onChange={(e) => setNewTicker(e.target.value)}
              disabled={loading}
              className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500 disabled:opacity-50 uppercase"
            />
          </div>

          <div className="w-full sm:w-36">
            <label className="block text-xs font-medium text-slate-400 mb-1">Target MoS %</label>
            <div className="relative">
              <input
                type="number"
                step="0.5"
                min="0"
                max="100"
                value={newTargetMos}
                onChange={(e) => setNewTargetMos(parseFloat(e.target.value) || 0)}
                disabled={loading}
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500 disabled:opacity-50 pr-8"
              />
              <span className="absolute right-3 top-2 text-xs text-slate-500">%</span>
            </div>
          </div>

          <div className="flex-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">Investment Note (Optional)</label>
            <input
              type="text"
              placeholder="e.g. Buying on 20% discount pullback"
              value={newNotes}
              onChange={(e) => setNewNotes(e.target.value)}
              disabled={loading}
              className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500 disabled:opacity-50"
            />
          </div>

          <div className="self-end pt-5">
            <button
              type="submit"
              disabled={loading || !newTicker.trim()}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-500 transition-colors disabled:opacity-50 h-[38px] w-full sm:w-auto"
            >
              <Plus className="h-4 w-4" />
              <span>Add to Watchlist</span>
            </button>
          </div>
        </form>

        {statusMessage && (
          <div
            className={`mt-3 flex items-center gap-2 text-xs font-medium ${
              statusMessage.type === 'success' ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {statusMessage.type === 'success' ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <AlertCircle className="h-3.5 w-3.5" />
            )}
            <span>{statusMessage.text}</span>
          </div>
        )}
      </div>

      {/* Watchlist Table */}
      {watchlist.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="border-b border-slate-800 bg-slate-900/80 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3.5">Ticker & Company</th>
                <th className="px-4 py-3.5">Sector</th>
                <th className="px-4 py-3.5">Current Price</th>
                <th className="px-4 py-3.5">Intrinsic Value</th>
                <th className="px-4 py-3.5">Current MoS</th>
                <th className="px-4 py-3.5">Target MoS</th>
                <th className="px-4 py-3.5">Alert Trigger</th>
                <th className="px-4 py-3.5">Notes</th>
                <th className="px-4 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {watchlist.map((item) => {
                const isPositiveMos = item.mosPct !== null && item.mosPct > 0;
                return (
                  <tr key={item.ticker} className="hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-3.5">
                      <Link href={`/stocks/${item.ticker}`} className="font-bold text-white hover:text-blue-400 transition-colors">
                        {item.ticker}
                      </Link>
                      <div className="text-xs text-slate-400 line-clamp-1">{item.name}</div>
                    </td>
                    <td className="px-4 py-3.5 text-xs text-slate-400">{item.sector}</td>
                    <td className="px-4 py-3.5 font-medium text-white">
                      {item.currentPrice ? `₱${item.currentPrice.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-4 py-3.5 text-slate-400">
                      {item.intrinsicValue ? `₱${item.intrinsicValue.toFixed(2)}` : 'N/A'}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`font-bold ${isPositiveMos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {item.mosPct !== null ? `${item.mosPct > 0 ? '+' : ''}${item.mosPct.toFixed(1)}%` : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-300 font-semibold">
                      +{item.targetMos?.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3.5">
                      {item.isTriggered ? (
                        <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400">
                          <Bell className="h-3 w-3" />
                          <span>Target Hit</span>
                        </span>
                      ) : (
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                          Monitoring
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-xs text-slate-400 max-w-[200px] truncate">
                      {item.notes || '—'}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          href={`/stocks/${item.ticker}`}
                          className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
                          title="View In-Depth Profile"
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
            Add equities with your target Margin of Safety threshold cushion to start tracking real-time intrinsic value alerts.
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
