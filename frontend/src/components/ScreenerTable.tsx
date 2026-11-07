'use client';

import React, { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import {
  Search,
  ArrowUpDown,
  ChevronRight,
  ShieldCheck,
  TrendingUp,
  Sparkles,
  Lock,
  Download,
  CheckCircle2,
  Zap,
  ArrowRight,
  Mail,
  Smartphone,
  CreditCard,
  RefreshCw,
} from 'lucide-react';
import { StockRanking } from '../types/stock';
import { outcomeApi, OutcomeAccess } from '@/lib/api';

interface ScreenerTableProps {
  initialStocks: StockRanking[];
}

export default function ScreenerTable({ initialStocks }: ScreenerTableProps) {
  const [search, setSearch] = useState('');
  const [selectedSector, setSelectedSector] = useState<string>('All');
  const [sortBy, setSortBy] = useState<keyof StockRanking>('rank');
  const [sortAsc, setSortAsc] = useState(true);

  // Outcome Access State
  const [outcome, setOutcome] = useState<OutcomeAccess | null>(null);
  const [unlockEmail, setUnlockEmail] = useState('');
  const [paymentChannel, setPaymentChannel] = useState<'gcash' | 'maya' | 'card'>('gcash');
  const [unlockLoading, setUnlockLoading] = useState(false);
  const [unlockMsg, setUnlockMsg] = useState<{ text: string; error?: boolean } | null>(null);

  useEffect(() => {
    const active = outcomeApi.getStoredOutcome();
    setOutcome(active);
  }, []);

  const isUnlocked = Boolean(outcome?.unlocked);

  const sectors = useMemo(() => {
    const list = Array.from(new Set(initialStocks.map((s) => s.sector)));
    return ['All', ...list.sort()];
  }, [initialStocks]);

  const filteredStocks = useMemo(() => {
    return initialStocks
      .filter((stock) => {
        const matchesSearch =
          stock.ticker.toLowerCase().includes(search.toLowerCase()) ||
          stock.name.toLowerCase().includes(search.toLowerCase());
        const matchesSector = selectedSector === 'All' || stock.sector === selectedSector;
        return matchesSearch && matchesSector;
      })
      .sort((a, b) => {
        const valA = a[sortBy];
        const valB = b[sortBy];
        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;
        if (valA < valB) return sortAsc ? -1 : 1;
        if (valA > valB) return sortAsc ? 1 : -1;
        return 0;
      });
  }, [initialStocks, search, selectedSector, sortBy, sortAsc]);

  const handleSort = (field: keyof StockRanking) => {
    if (sortBy === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortBy(field);
      if (['score', 'mosPct', 'roe', 'dividendYield'].includes(field)) {
        setSortAsc(false);
      } else {
        setSortAsc(true);
      }
    }
  };

  const getCategoryBadge = (category: string) => {
    switch (category) {
      case 'Highest Quality':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'Strong Growth':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'Watchlist':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      default:
        return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
    }
  };

  const handleQuickUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    setUnlockMsg(null);
    const cleanEmail = unlockEmail.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes('@') || !cleanEmail.includes('.')) {
      setUnlockMsg({ text: 'Please provide a valid email address.', error: true });
      return;
    }

    setUnlockLoading(true);
    try {
      const res = await outcomeApi.checkoutOnDemand(cleanEmail, paymentChannel, undefined, 499.0);
      setOutcome({
        email: cleanEmail,
        unlocked: true,
        tier: 'paid',
        plan: 'on_demand',
        downloadUrl: res.download_url,
      });
      setUnlockMsg({ text: 'Outcome Pass activated! Full valuations unlocked.', error: false });
    } catch (err: any) {
      setUnlockMsg({ text: 'Checkout failed. Please retry.', error: true });
    } finally {
      setUnlockLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Outcome Status Banner */}
      {isUnlocked ? (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-950/20 px-5 py-3.5 backdrop-blur-sm">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
            <div>
              <span className="text-xs font-bold text-white">
                Outcome Pass Active ({outcome?.email})
              </span>
              <p className="text-[11px] text-emerald-300/80">
                Full 50+ stock universe, intrinsic DCF values, and Margin of Safety cushions unlocked.
              </p>
            </div>
          </div>
          <a
            href="http://127.0.0.1:8000/api/v1/reports/download-latest"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 self-start sm:self-center rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md shadow-emerald-600/20 hover:bg-emerald-500 transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Download A4 PDF</span>
          </a>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-2xl border border-blue-500/30 bg-blue-950/20 px-5 py-3.5 backdrop-blur-sm">
          <div className="flex items-center gap-2.5">
            <Zap className="h-4 w-4 text-amber-400 shrink-0" />
            <div className="text-xs text-slate-300">
              <span className="font-bold text-white">Preview Mode:</span> Top equities shown in full. 
              Unlock all 50+ scored companies &amp; DCF calculations on demand for a flat ₱499.
            </div>
          </div>
          <a
            href="#quick-unlock"
            onClick={(e) => {
              e.preventDefault();
              const el = document.getElementById('quick-unlock');
              if (el) el.scrollIntoView({ behavior: 'smooth' });
            }}
            className="inline-flex items-center gap-1 self-start sm:self-center text-xs font-bold text-blue-400 hover:text-blue-300 underline underline-offset-4"
          >
            <span>Unlock Universe (₱499)</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </a>
        </div>
      )}

      {/* Controls: Search and Sector Tabs */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by ticker or company name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-slate-800 bg-slate-900/60 py-2 pl-9 pr-4 text-sm text-slate-100 placeholder-slate-400 outline-none transition-all focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="flex flex-wrap gap-1.5">
          {sectors.map((sec) => (
            <button
              key={sec}
              onClick={() => setSelectedSector(sec)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                selectedSector === sec
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              {sec}
            </button>
          ))}
        </div>
      </div>

      {/* Table Container */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40 backdrop-blur-sm">
        <table className="w-full text-left text-sm text-slate-300">
          <thead className="border-b border-slate-800 bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400">
            <tr>
              <th className="px-4 py-3.5 cursor-pointer" onClick={() => handleSort('rank')}>
                <div className="flex items-center gap-1">
                  <span>Rank</span>
                  <ArrowUpDown className="h-3 w-3" />
                </div>
              </th>
              <th className="px-4 py-3.5 cursor-pointer" onClick={() => handleSort('ticker')}>
                <div className="flex items-center gap-1">
                  <span>Ticker</span>
                  <ArrowUpDown className="h-3 w-3" />
                </div>
              </th>
              <th className="px-4 py-3.5">Sector</th>
              <th className="px-4 py-3.5 cursor-pointer" onClick={() => handleSort('score')}>
                <div className="flex items-center gap-1">
                  <span>Score</span>
                  <ArrowUpDown className="h-3 w-3" />
                </div>
              </th>
              <th className="px-4 py-3.5">Quality Band</th>
              <th className="px-4 py-3.5 cursor-pointer" onClick={() => handleSort('currentPrice')}>
                <div className="flex items-center gap-1">
                  <span>Price</span>
                  <ArrowUpDown className="h-3 w-3" />
                </div>
              </th>
              <th className="px-4 py-3.5 cursor-pointer" onClick={() => handleSort('intrinsicValue')}>
                <div className="flex items-center gap-1">
                  <span>Intrinsic Val.</span>
                  <ArrowUpDown className="h-3 w-3" />
                </div>
              </th>
              <th className="px-4 py-3.5 cursor-pointer" onClick={() => handleSort('mosPct')}>
                <div className="flex items-center gap-1">
                  <span>Margin of Safety</span>
                  <ArrowUpDown className="h-3 w-3" />
                </div>
              </th>
              <th className="px-4 py-3.5 cursor-pointer" onClick={() => handleSort('dividendYield')}>
                <div className="flex items-center gap-1">
                  <span>Div. Yield</span>
                  <ArrowUpDown className="h-3 w-3" />
                </div>
              </th>
              <th className="px-4 py-3.5 text-right">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filteredStocks.length > 0 ? (
              filteredStocks.map((stock, index) => {
                const isPositiveMos = stock.mosPct !== null && stock.mosPct > 0;
                // If not unlocked, stocks beyond index 4 (rank 6+) are blurred in valuation
                const isLockedRow = !isUnlocked && index >= 5;

                return (
                  <tr
                    key={stock.ticker}
                    className="group transition-colors hover:bg-slate-800/40"
                  >
                    <td className="px-4 py-3.5 font-semibold text-slate-400">
                      #{stock.rank}
                    </td>
                    <td className="px-4 py-3.5">
                      <Link href={`/stocks/${stock.ticker}`} className="flex flex-col">
                        <span className="font-bold text-white group-hover:text-blue-400 transition-colors">
                          {stock.ticker}
                        </span>
                        <span className="text-xs text-slate-400 line-clamp-1">
                          {stock.name}
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-3.5 text-xs text-slate-400">
                      <span className="rounded bg-slate-800 px-2 py-0.5 font-medium text-slate-300">
                        {stock.scoringGroup}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-extrabold text-white">
                          {stock.score.toFixed(1)}
                        </span>
                        <div className="h-1.5 w-12 rounded-full bg-slate-800 overflow-hidden">
                          <div
                            className="h-full bg-blue-500 rounded-full"
                            style={{ width: `${Math.min(100, stock.score)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${getCategoryBadge(
                          stock.category
                        )}`}
                      >
                        <ShieldCheck className="h-3 w-3" />
                        {stock.category}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-medium text-slate-200">
                      ₱{stock.currentPrice.toFixed(2)}
                    </td>

                    {/* Intrinsic Value Cell */}
                    <td className="px-4 py-3.5 text-slate-400">
                      {isLockedRow ? (
                        <div className="flex items-center gap-1.5 text-xs text-slate-500 blur-[3px] select-none">
                          <span>₱48.50</span>
                        </div>
                      ) : (
                        stock.intrinsicValue ? `₱${stock.intrinsicValue.toFixed(2)}` : 'N/A'
                      )}
                    </td>

                    {/* Margin of Safety Cell */}
                    <td className="px-4 py-3.5">
                      {isLockedRow ? (
                        <div className="flex items-center gap-1 text-xs text-slate-500 blur-[3px] select-none">
                          <span>+18.4%</span>
                        </div>
                      ) : stock.mosPct !== null ? (
                        <span
                          className={`inline-flex items-center font-bold text-xs ${
                            isPositiveMos ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {isPositiveMos ? `+${stock.mosPct.toFixed(1)}%` : `${stock.mosPct.toFixed(1)}%`}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">N/A</span>
                      )}
                    </td>

                    <td className="px-4 py-3.5 font-medium text-slate-300">
                      {stock.dividendYield ? `${stock.dividendYield.toFixed(2)}%` : '—'}
                    </td>

                    <td className="px-4 py-3.5 text-right">
                      <Link
                        href={`/stocks/${stock.ticker}`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-blue-400 hover:text-blue-300"
                      >
                        <span>Analyze</span>
                        <ChevronRight className="h-3.5 w-3.5" />
                      </Link>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-slate-400">
                  No stocks found matching your criteria.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Inline Quick Unlock Card (when not yet unlocked) */}
      {!isUnlocked && (
        <div
          id="quick-unlock"
          className="rounded-2xl border border-blue-500/30 bg-gradient-to-r from-slate-900 via-blue-950/40 to-slate-900 p-6 backdrop-blur-md shadow-xl"
        >
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div className="max-w-xl">
              <div className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/20 border border-blue-500/30 px-2.5 py-0.5 text-[11px] font-bold text-blue-300 uppercase tracking-wider mb-2">
                <Lock className="h-3 w-3" />
                Outcome as a Service
              </div>
              <h3 className="text-xl font-extrabold text-white">
                Unlock Complete 2026 PSE Universe &amp; DCF Calculations
              </h3>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                Gain instant on-demand access to all 50+ scored stocks, intrinsic DCF discount cushions, and receive the executive A4 PDF research dossier in your inbox for a flat ₱499. No recurring monthly SaaS bills.
              </p>
            </div>

            <div className="w-full lg:max-w-md">
              <form onSubmit={handleQuickUnlock} className="flex flex-col sm:flex-row gap-2">
                <div className="relative flex-1">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="email"
                    required
                    placeholder="Enter email for instant unlock..."
                    value={unlockEmail}
                    onChange={(e) => setUnlockEmail(e.target.value)}
                    disabled={unlockLoading}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-10 pr-3 text-xs text-white placeholder-slate-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={unlockLoading}
                  className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-md shadow-blue-600/30 hover:bg-blue-500 transition-all shrink-0 cursor-pointer disabled:opacity-60"
                >
                  {unlockLoading ? (
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <>
                      <span>Pay ₱499 &amp; Unlock</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </form>

              {unlockMsg && (
                <p className={`text-xs mt-2 ${unlockMsg.error ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {unlockMsg.text}
                </p>
              )}

              <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
                <span>GCash • Maya • Card</span>
                <Link href="/login" className="underline hover:text-white">
                  Already paid? Restore access
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
