'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { User, ShieldCheck, Mail, ArrowRight, Zap, Bell, CheckCircle } from 'lucide-react';

export default function MemberGreeting() {
  const [user, setUser] = useState<{ email: string; name?: string; tier?: string } | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem('stockpilot_member_user');
    const token = localStorage.getItem('stockpilot_member_token');
    if (stored && token) {
      try {
        setUser(JSON.parse(stored));
      } catch (e) {
        setUser(null);
      }
    }
  }, []);

  if (!mounted) return null;

  if (user) {
    return (
      <div className="rounded-2xl border border-blue-500/20 bg-gradient-to-r from-blue-950/40 via-slate-900/60 to-indigo-950/30 p-5 backdrop-blur-sm shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/20 border border-blue-500/40 text-blue-400">
              <User className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white">
                  {user.name ? `${user.name} (${user.email})` : user.email}
                </span>
                <span className="rounded-full bg-blue-500/20 border border-blue-500/30 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-blue-300">
                  {user.tier || 'Member'} Plan
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Automated weekly research digest and pre-market price trigger alerts active.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/watchlist"
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition-colors"
            >
              <Zap className="h-3.5 w-3.5 text-amber-400" />
              <span>Watchlist</span>
            </Link>
            <div className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5 font-medium">
              <CheckCircle className="h-3.5 w-3.5" />
              <span>Email Synced</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900/80 to-blue-950/30 p-5 backdrop-blur-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <span>Unlock Personalized Watchlists & Morning Alerts</span>
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Create a free account or sign in to receive pre-market PSE email alerts and track intrinsic Margin-of-Safety targets.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-blue-600/25 hover:bg-blue-500 transition-colors"
          >
            <span>Sign In / Register</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}