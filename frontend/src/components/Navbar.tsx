'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Compass, Bookmark, TrendingUp, Sparkles, LayoutDashboard, User, LogOut } from 'lucide-react';

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [memberUser, setMemberUser] = useState<{ email: string; name?: string; tier?: string } | null>(null);

  useEffect(() => {
    // Check if member is logged in
    const storedUser = localStorage.getItem('stockpilot_member_user');
    const token = localStorage.getItem('stockpilot_member_token');
    if (storedUser && token) {
      try {
        setMemberUser(JSON.parse(storedUser));
      } catch (e) {
        setMemberUser(null);
      }
    } else {
      setMemberUser(null);
    }
  }, [pathname]);

  // If inside the admin portal, do not render the consumer navbar
  if (pathname?.startsWith('/admin')) {
    return null;
  }

  const handleSignOut = () => {
    localStorage.removeItem('stockpilot_member_token');
    localStorage.removeItem('stockpilot_member_user');
    setMemberUser(null);
    router.push('/login');
  };

  const navLinks = [
    { href: '/', label: 'Overview' },
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/screener', label: 'Rankings Screener', icon: Compass },
    { href: '/watchlist', label: 'Watchlist', icon: Bookmark },
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

        <div className="flex items-center gap-3">
          <Link
            href="/screener"
            className="hidden sm:flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md shadow-blue-600/25 transition-all hover:brightness-110"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Top Rankings</span>
          </Link>

          {memberUser ? (
            <div className="flex items-center gap-2">
              <div className="hidden sm:flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-1.5 text-xs">
                <User className="h-3.5 w-3.5 text-blue-400" />
                <span className="max-w-[140px] truncate text-slate-200 font-medium">
                  {memberUser.email}
                </span>
                <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-blue-300 uppercase">
                  {memberUser.tier || 'Member'}
                </span>
              </div>
              <button
                onClick={handleSignOut}
                title="Sign Out"
                className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3.5 py-1.5 text-xs font-semibold text-blue-400 hover:bg-blue-500/20 hover:text-blue-300 transition-all"
            >
              <User className="h-3.5 w-3.5" />
              <span>Sign In</span>
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
