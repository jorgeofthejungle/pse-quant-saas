'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { User, ShieldCheck, Mail, ArrowRight, Zap, Bell, CheckCircle, Download } from 'lucide-react';
import { outcomeApi, OutcomeAccess } from '@/lib/api';

export default function MemberGreeting() {
  const [outcome, setOutcome] = useState<OutcomeAccess | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const active = outcomeApi.getStoredOutcome();
    setOutcome(active);
  }, []);

  if (!mounted) return null;

  if (outcome && outcome.unlocked) {
    return (
      <div className="rounded-2xl border border-emerald-500/30 bg-gradient-to-r from-slate-900 via-slate-900/90 to-emerald-950/30 p-5 backdrop-blur-sm shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-400">
              <CheckCircle className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white">
                  {outcome.email}
                </span>
                <span className="rounded-full bg-emerald-500/20 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                  Outcome Pass Active
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                On-demand intelligence unlocked. Research dossier and pre-market price alerts dispatched to your inbox.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <a
              href="http://127.0.0.1:8000/api/v1/reports/download-latest"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md shadow-emerald-600/25 hover:bg-emerald-500 transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              <span>Download PDF</span>
            </a>
            <Link
              href="/watchlist"
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition-colors"
            >
              <Zap className="h-3.5 w-3.5 text-amber-400" />
              <span>My Watchlist</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-blue-500/20 bg-gradient-to-r from-slate-900/90 to-blue-950/40 p-5 backdrop-blur-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-blue-400 mb-1.5">
            <Zap className="h-3 w-3 text-amber-400" />
            <span>Outcome as a Service</span>
          </div>
          <h3 className="text-sm font-bold text-white">
            Unlock Full Institutional Research &amp; Margin of Safety Alerts
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Pay a flat ₱499 fixed fee on demand. Zero monthly subscriptions, zero passwords. Enter your email and you&apos;re good to go.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <Link
            href="/login"
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-md shadow-blue-600/25 hover:bg-blue-500 transition-colors"
          >
            <span>Unlock for ₱499</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}
