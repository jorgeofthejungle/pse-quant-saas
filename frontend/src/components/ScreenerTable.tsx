'use client';

import React, { useState, useMemo } from 'react';
import Link from 'next/link';
import { Search, ArrowUpDown, ChevronRight, ShieldCheck, TrendingUp, Sparkles } from 'lucide-react';
import { StockRanking } from '../types/stock';

interface ScreenerTableProps {
  initialStocks: StockRanking[];
}

export default function ScreenerTable({ initialStocks }: ScreenerTableProps) {
  const [search, setSearch] = useState('');
  const [selectedSector, setSelectedSector] = useState<string>('All');
  const [sortBy, setSortBy] = useState<keyof StockRanking>('rank');
  const [sortAsc, setSortAsc] = useState(true);

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
      // For score, mosPct, roe, yield, sort descending by default
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

  return (
    <div className="space-y-4">
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
              filteredStocks.map((stock) => {
                const isPositiveMos = stock.mosPct !== null && stock.mosPct > 0;
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
                    <td className="px-4 py-3.5 text-slate-400">
                      {stock.intrinsicValue ? `₱${stock.intrinsicValue.toFixed(2)}` : 'N/A'}
                    </td>
                    <td className="px-4 py-3.5">
                      {stock.mosPct !== null ? (
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
    </div>
  );
}
