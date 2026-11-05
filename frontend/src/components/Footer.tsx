'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Footer() {
  const pathname = usePathname();

  // If inside the admin portal, do not render consumer footer
  if (pathname?.startsWith('/admin')) {
    return null;
  }

  return (
    <footer className="border-t border-slate-800 bg-slate-950 py-12 text-slate-400">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-4">
          <div className="md:col-span-2">
            <span className="text-lg font-bold text-white">StockPilot PH</span>
            <p className="mt-3 max-w-md text-sm text-slate-400">
              A deterministic multi-factor Philippine equity ranking and intrinsic value valuation engine. Delivering weekly PDF research reports and daily pre-market alerts directly to subscribers.
            </p>
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-200">Platform</h4>
            <ul className="mt-3 space-y-2 text-sm">
              <li><Link href="/screener" className="hover:text-white">Rankings Screener</Link></li>
              <li><Link href="/watchlist" className="hover:text-white">Personal Watchlist</Link></li>
              <li><Link href="/dashboard" className="hover:text-white">Command Dashboard</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-200">Legal</h4>
            <ul className="mt-3 space-y-2 text-sm">
              <li className="text-xs leading-relaxed text-slate-400">
                Educational research only. Not financial advice, solicitations, or recommendations.
              </li>
            </ul>
          </div>
        </div>
        <div className="mt-8 border-t border-slate-800/80 pt-8 text-center text-xs text-slate-400">
          © 2026 StockPilot PH. Built for Philippine equity investors.
        </div>
      </div>
    </footer>
  );
}
