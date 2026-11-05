'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ShieldAlert,
  Lock,
  Mail,
  AlertTriangle,
  ArrowRight,
  Terminal,
  KeyRound,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import { authApi } from '@/lib/api';

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAccessDenied, setIsAccessDenied] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsAccessDenied(false);
    setLoading(true);

    try {
      const data = await authApi.loginAdmin(email, password);
      localStorage.setItem('stockpilot_admin_token', data.access_token);
      localStorage.setItem(
        'stockpilot_admin_user',
        JSON.stringify({
          id: data.user.id,
          email: data.user.email,
          role: data.user.role,
        })
      );
      router.push('/admin');
    } catch (err: any) {
      const msg = err.message || 'Access denied: Invalid administrator credentials';
      setError(msg);
      if (msg.includes('restricted') || msg.includes('Administrator') || msg.includes('denied')) {
        setIsAccessDenied(true);
      }
    } finally {
      setLoading(false);
    }
  };

  const fillAdminCredentials = () => {
    setEmail('admin@stockpilot.ph');
    setPassword('AdminPass123!');
    setError(null);
    setIsAccessDenied(false);
  };

  const fillMemberCredentials = () => {
    setEmail('member@investor.ph');
    setPassword('MemberPass123!');
    setError(null);
    setIsAccessDenied(false);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 py-12 sm:px-6 lg:px-8 font-sans selection:bg-rose-500 selection:text-white">
      <div className="w-full max-w-md space-y-8">
        {/* Terminal Header */}
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-rose-500/40 bg-rose-500/10 text-rose-400 shadow-xl shadow-rose-950/50">
            <ShieldAlert className="h-8 w-8" />
          </div>
          <div className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-0.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-rose-400">
            <Terminal className="h-3 w-3" />
            <span>OPERATOR ACCESS ONLY</span>
          </div>
          <h2 className="mt-3 text-2xl font-black tracking-tight text-white font-mono uppercase sm:text-3xl">
            StockPilot Gateway
          </h2>
          <p className="mt-1 text-xs font-mono text-slate-400">
            SECURE ACCESS GATE • QUANT DECISION ENGINE v2.0
          </p>
        </div>

        {/* Warning Banner */}
        <div className="rounded-xl border border-rose-900/60 bg-rose-950/20 p-4 text-xs font-mono text-rose-300 backdrop-blur-sm">
          <div className="flex items-center gap-2 font-bold text-rose-400 mb-1">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>RESTRICTED PRODUCTION ENVIRONMENT</span>
          </div>
          <p className="text-[11px] leading-relaxed text-slate-400">
            Direct operational access to backend data scrapers, valuation recalculation, customer database, and email dispatch engines. Unauthorized attempts are cryptographically rejected and logged.
          </p>
        </div>

        {/* Error / Denial Alert */}
        {error && (
          <div
            className={`flex items-start gap-2.5 rounded-xl border p-4 text-xs font-mono ${
              isAccessDenied
                ? 'border-red-500/50 bg-red-950/40 text-red-200'
                : 'border-amber-500/40 bg-amber-950/30 text-amber-200'
            }`}
          >
            <AlertCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
            <div className="space-y-1">
              <div className="font-bold uppercase tracking-wider text-red-400">
                {isAccessDenied ? 'ACCESS VIOLATION: CLEARANCE DENIED' : 'AUTHENTICATION FAILED'}
              </div>
              <div className="text-[11px] leading-relaxed text-slate-300">{error}</div>
              {isAccessDenied && (
                <div className="mt-2 text-[10px] text-red-400/80">
                  Notice: Regular member credentials cannot authenticate into this terminal.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Login Form */}
        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-2xl border border-rose-900/40 bg-slate-900/80 p-6 backdrop-blur-md shadow-2xl shadow-rose-950/30"
        >
          <div>
            <label className="block text-xs font-mono font-medium text-slate-300 mb-1.5 uppercase">
              Administrator Email
            </label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@stockpilot.ph"
                className="w-full rounded-lg border border-slate-700 bg-slate-950/90 py-2.5 pl-10 pr-4 text-sm font-mono text-white placeholder-slate-600 focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono font-medium text-slate-300 mb-1.5 uppercase">
              Security Key / Password
            </label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-slate-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full rounded-lg border border-slate-700 bg-slate-950/90 py-2.5 pl-10 pr-4 text-sm font-mono text-white placeholder-slate-600 focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-rose-600 py-3 text-xs font-mono font-bold uppercase tracking-wider text-white shadow-lg shadow-rose-600/30 transition-all hover:bg-rose-500 hover:shadow-rose-600/40 disabled:opacity-50"
          >
            {loading ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <>
                <ShieldAlert className="h-4 w-4" />
                <span>Authenticate Operator</span>
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>

          {/* Quick Demo Fill Buttons */}
          <div className="mt-4 space-y-2 border-t border-slate-800/80 pt-4">
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 text-center">
              Quick Test Credentials:
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={fillAdminCredentials}
                className="flex items-center justify-center gap-1 rounded-md border border-rose-800/60 bg-rose-950/40 py-1.5 px-2 text-[10px] font-mono text-rose-300 hover:bg-rose-900/50 transition-colors"
              >
                <KeyRound className="h-3 w-3" />
                <span>Fill Admin (200 OK)</span>
              </button>
              <button
                type="button"
                onClick={fillMemberCredentials}
                className="flex items-center justify-center gap-1 rounded-md border border-slate-800 bg-slate-900/60 py-1.5 px-2 text-[10px] font-mono text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
              >
                <AlertCircle className="h-3 w-3 text-amber-400" />
                <span>Fill Member (403 Test)</span>
              </button>
            </div>
          </div>
        </form>

        {/* Member Portal Escape Hatch */}
        <div className="text-center">
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span>Looking for the retail investor portal? Go to Member Sign In</span>
            <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
      </div>
    </div>
  );
}