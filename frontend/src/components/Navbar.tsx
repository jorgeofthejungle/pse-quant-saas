'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Compass,
  Bookmark,
  TrendingUp,
  Sparkles,
  LayoutDashboard,
  User,
  LogOut,
  Download,
  Zap,
  CheckCircle2,
} from 'lucide-react';
import { outcomeApi, OutcomeAccess } from '@/lib/api';

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [outcome, setOutcome] = useState<OutcomeAccess | null>(null);

  useEffect(() => {
    // Check if outcome access or member session is present
    const active = outcomeApi.getStoredOutcome();
    setOutcome(active);
  }, [pathname]);

  // If inside the admin portal, do not render the consumer navbar
  if (pathname?.startsWith('/admin')) {
    return null;
  }

  const handleClearAccess = () => {
    outcomeApi.clearStoredOutcome();
    setOutcome(null);
    router.push('/');
  };

  const navLinks = [
    { href: '/', label: 'Request Report' },
    { href: '/screener', label: 'Rankings Screener', icon: Compass },
    { href: '/dashboard', label: 'Done-For-You Hub', icon: LayoutDashboard },
  ];

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white shadow-md shadow-blue-500/20">
              <TrendingUp className="h-5 w-5" />
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight text-white">StockPilot</span>
              <span className="ml-1 text-xs font-semibold uppercase tracking-wider text-amber-400">PH</span>
            </div>
          </Link>

          <nav className="hidden md:flex md:items-center md:gap-1">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              const Icon = link.icon;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-slate-800 text-white'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                  }`}
                >
                  {Icon && <Icon className="h-4 w-4" />}
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-2.5 sm:gap-3">
          {outcome && outcome.unlocked ? (
            <div className="flex items-center gap-2">
              <a
                href="http://127.0.0.1:8000/api/v1/reports/download-latest"
                target="_blank"
                rel="noopener noreferrer"
                title="Download Latest PDF Dossier"
                className="hidden sm:flex items-center gap-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-all"
              >
                <Download className="h-3.5 w-3.5" />
                <span>PDF Report</span>
              </a>

              <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/90 px-3 py-1.5 text-xs">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                <span className="max-w-[120px] sm:max-w-[160px] truncate text-slate-200 font-medium">
                  {outcome.email}
                </span>
                <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 text-[9px] font-bold text-emerald-300 uppercase tracking-wider">
                  Paid
                </span>
              </div>

              <button
                onClick={handleClearAccess}
                title="Switch Email / Clear Session"
                className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Switch</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                href="/"
                className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-md shadow-blue-600/25 transition-all hover:brightness-110"
              >
                <Zap className="h-3.5 w-3.5 text-amber-300" />
                <span>Request Report (PWYC)</span>
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
