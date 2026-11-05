'use client';

import React, { useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ShieldAlert,
  Server,
  LogOut,
  Terminal,
  Activity,
  Layers,
  Users,
  Database,
  Lock,
} from 'lucide-react';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [operator, setOperator] = useState<{ email: string; role: string } | null>(null);
  const [mounted, setMounted] = useState(false);

  const isLoginPage = pathname === '/admin/login';

  useEffect(() => {
    setMounted(true);
    if (!isLoginPage) {
      const token = localStorage.getItem('stockpilot_admin_token');
      const userStr = localStorage.getItem('stockpilot_admin_user');
      if (!token) {
        router.push('/admin/login');
        return;
      }
      if (userStr) {
        try {
          const parsed = JSON.parse(userStr);
          if (parsed.role !== 'admin') {
            localStorage.removeItem('stockpilot_admin_token');
            localStorage.removeItem('stockpilot_admin_user');
            router.push('/admin/login');
            return;
          }
          setOperator(parsed);
        } catch (e) {
          setOperator({ email: 'admin@stockpilot.ph', role: 'admin' });
        }
      } else {
        setOperator({ email: 'admin@stockpilot.ph', role: 'admin' });
      }
    }
  }, [pathname, isLoginPage, router]);

  const handleLogout = () => {
    localStorage.removeItem('stockpilot_admin_token');
    localStorage.removeItem('stockpilot_admin_user');
    setOperator(null);
    router.push('/admin/login');
  };

  // If on login page, just render children without operator navigation
  if (isLoginPage) {
    return <div className="min-h-screen bg-slate-950 text-slate-100">{children}</div>;
  }

  // Prevent flicker during initial token verification
  if (!mounted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
        <div className="flex items-center gap-3">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-rose-500 border-t-transparent" />
          <span className="text-xs font-mono tracking-widest text-slate-400 uppercase">
            Verifying Operator Clearance...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans antialiased selection:bg-rose-500 selection:text-white">
      {/* ── High-Security Top Command Header ────────────────── */}
      <header className="sticky top-0 z-50 border-b border-rose-900/40 bg-slate-950/95 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Brand & Mode */}
          <div className="flex items-center gap-4">
            <Link href="/admin" className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-600/20 border border-rose-500/40 text-rose-400 shadow-sm shadow-rose-900/30">
                <ShieldAlert className="h-4 w-4" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-bold tracking-wider uppercase text-white font-mono">
                  StockPilot
                </span>
                <span className="rounded bg-rose-500/20 border border-rose-500/30 px-1.5 py-0.5 text-[10px] font-mono font-bold tracking-wider uppercase text-rose-400">
                  OPERATOR CONSOLE
                </span>
              </div>
            </Link>

            <div className="hidden lg:flex items-center gap-1.5 border-l border-slate-800 pl-4 text-[11px] font-mono text-slate-400">
              <Terminal className="h-3 w-3 text-slate-500" />
              <span>DIRECT SERVER CONTROL</span>
            </div>
          </div>

          {/* Center: Live Server Telemetry */}
          <div className="hidden md:flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900/90 px-3 py-1 text-xs font-mono">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
              </span>
              <span className="text-slate-400">BACKEND:</span>
              <span className="text-emerald-400 font-semibold">127.0.0.1:8000 (HEALTHY)</span>
            </div>
          </div>

          {/* Right: Operator Badge & Lock Button */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-lg border border-rose-900/40 bg-rose-950/30 px-3 py-1 text-xs font-mono">
              <Lock className="h-3 w-3 text-rose-400" />
              <span className="text-slate-300 truncate max-w-[150px]">
                {operator?.email || 'admin@stockpilot.ph'}
              </span>
              <span className="rounded bg-rose-500/30 px-1 text-[9px] font-bold uppercase text-rose-300">
                ADMIN
              </span>
            </div>

            <button
              onClick={handleLogout}
              title="Terminate Operator Session"
              className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-rose-800 hover:bg-rose-950/40 hover:text-rose-300 transition-colors"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Lock Console</span>
            </button>
          </div>
        </div>
      </header>

      {/* ── Sub-navigation Strip ───────────────────────────── */}
      <div className="border-b border-slate-800/80 bg-slate-900/40 px-4 py-2 text-xs">
        <div className="mx-auto flex max-w-7xl items-center justify-between text-slate-400">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-slate-300 font-medium">
              <Activity className="h-3.5 w-3.5 text-rose-400" />
              <span>Operational Modules:</span>
            </span>
            <span className="hover:text-white cursor-pointer transition-colors">Pipeline Orchestration</span>
            <span className="text-slate-600">•</span>
            <span className="hover:text-white cursor-pointer transition-colors">Data Ingestion</span>
            <span className="text-slate-600">•</span>
            <span className="hover:text-white cursor-pointer transition-colors">Customer Registry</span>
            <span className="text-slate-600">•</span>
            <span className="hover:text-white cursor-pointer transition-colors">Manual Financials Override</span>
          </div>

          <div className="hidden sm:flex items-center gap-2 text-[11px] font-mono text-slate-500">
            <span>SECURE RESTRICTED SESSION</span>
          </div>
        </div>
      </div>

      {/* ── Main Content Area ──────────────────────────────── */}
      <main className="flex-1">{children}</main>

      {/* ── Admin Operations Footer ────────────────────────── */}
      <footer className="border-t border-rose-900/30 bg-slate-950/90 py-4 text-xs font-mono text-slate-500">
        <div className="mx-auto flex max-w-7xl flex-col sm:flex-row items-center justify-between px-4 sm:px-6 lg:px-8 gap-2">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
            <span>STOCKPILOT QUANT DECISION SERVER v2.0 • INTERNAL SYSTEM CONTROLS</span>
          </div>
          <div>
            <span>UNAUTHORIZED ACCESS STRICTLY MONITORED & PROSECUTED UNDER RA 10175</span>
          </div>
        </div>
      </footer>
    </div>
  );
}