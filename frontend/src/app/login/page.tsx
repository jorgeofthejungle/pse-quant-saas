'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TrendingUp, Lock, Mail, User, ArrowRight, ShieldCheck, CheckCircle2, AlertCircle, KeyRound } from 'lucide-react';
import { authApi } from '@/lib/api';

export default function MemberLoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    setLoading(true);

    try {
      if (mode === 'login') {
        const data = await authApi.loginMember(email, password);
        localStorage.setItem('stockpilot_member_token', data.access_token);
        localStorage.setItem(
          'stockpilot_member_user',
          JSON.stringify({
            id: data.user.id,
            email: data.user.email,
            name: data.user.name,
            role: data.user.role,
            tier: data.user.tier,
          })
        );
        router.push('/dashboard');
      } else {
        const data = await authApi.registerMember(email, password, name);
        localStorage.setItem('stockpilot_member_token', data.access_token);
        localStorage.setItem(
          'stockpilot_member_user',
          JSON.stringify({
            id: data.user.id,
            email: data.user.email,
            name: data.user.name,
            role: data.user.role,
            tier: data.user.tier,
          })
        );
        setSuccessMsg('Account created successfully! Redirecting to your dashboard...');
        setTimeout(() => {
          router.push('/dashboard');
        }, 1000);
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleUseDemo = () => {
    setEmail('member@investor.ph');
    setPassword('MemberPass123!');
    setMode('login');
    setError(null);
  };

  return (
    <div className="flex min-h-[calc(100vh-10rem)] items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8">
        {/* Brand Header */}
        <div className="text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-500/25">
            <TrendingUp className="h-7 w-7" />
          </div>
          <h2 className="mt-5 text-3xl font-extrabold tracking-tight text-white">
            {mode === 'login' ? 'Welcome back to StockPilot' : 'Start your Free Membership'}
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            {mode === 'login'
              ? 'Access institutional-grade Philippine equity rankings & valuation models'
              : 'Join Philippine investors using quantitative Margin-of-Safety screeners'}
          </p>
        </div>

        {/* Tab Toggle */}
        <div className="grid grid-cols-2 gap-1 rounded-xl border border-slate-800 bg-slate-900/80 p-1 backdrop-blur-sm">
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setError(null);
            }}
            className={`rounded-lg py-2 text-xs font-semibold transition-all ${
              mode === 'login'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('register');
              setError(null);
            }}
            className={`rounded-lg py-2 text-xs font-semibold transition-all ${
              mode === 'register'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Create Free Account
          </button>
        </div>

        {/* Status Alerts */}
        {error && (
          <div className="flex items-start gap-2.5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-xs text-red-300">
            <AlertCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
            <div className="flex-1">{error}</div>
          </div>
        )}

        {successMsg && (
          <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" />
            <div className="flex-1">{successMsg}</div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-md shadow-xl">
          {mode === 'register' && (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Full Name (Optional)
              </label>
              <div className="relative">
                <User className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Juan dela Cruz"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/80 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Email Address
            </label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="investor@example.ph"
                className="w-full rounded-lg border border-slate-700 bg-slate-950/80 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Password
            </label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-slate-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full rounded-lg border border-slate-700 bg-slate-950/80 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/30 transition-all hover:bg-blue-500 hover:shadow-blue-600/40 disabled:opacity-50"
          >
            {loading ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <>
                <span>{mode === 'login' ? 'Sign In to Dashboard' : 'Create Free Account'}</span>
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>

          {/* Demo helper */}
          <div className="mt-4 border-t border-slate-800/80 pt-4 text-center">
            <button
              type="button"
              onClick={handleUseDemo}
              className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
            >
              <KeyRound className="h-3.5 w-3.5" />
              <span>Fill Demo Investor Credentials (member@investor.ph)</span>
            </button>
          </div>
        </form>

        {/* Feature Badges */}
        <div className="flex items-center justify-center gap-6 text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="h-4 w-4 text-blue-400" />
            <span>256-Bit Encrypted</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="h-4 w-4 text-blue-400" />
            <span>Daily Email Alerts</span>
          </div>
        </div>

        {/* Public Screener Link */}
        <div className="text-center">
          <Link
            href="/screener"
            className="text-xs text-slate-400 hover:text-slate-200 transition-colors underline underline-offset-4"
          >
            Or browse public PSE rankings without an account →
          </Link>
        </div>
      </div>
    </div>
  );
}