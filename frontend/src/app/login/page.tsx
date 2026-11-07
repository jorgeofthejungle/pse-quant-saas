'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TrendingUp, Lock, Zap, ArrowRight, ShieldCheck, CheckCircle2 } from 'lucide-react';
import OnDemandCheckoutCard from '@/components/OnDemandCheckoutCard';

export default function MemberLoginPage() {
  const router = useRouter();

  const handleUnlocked = (email: string) => {
    // When unlocked, give user a second to see confirmation, then navigate to dashboard
    setTimeout(() => {
      router.push('/dashboard');
    }, 1800);
  };

  return (
    <div className="flex min-h-[calc(100vh-10rem)] items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-lg space-y-8">
        {/* Brand Header */}
        <div className="text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-500/25">
            <TrendingUp className="h-7 w-7" />
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-400 mt-4">
            <Zap className="h-3.5 w-3.5 text-amber-400" />
            <span>Outcome as a Service</span>
          </div>
          <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-white">
            Customer Intelligence Access
          </h2>
          <p className="mt-2 text-sm text-slate-400 max-w-md mx-auto">
            Zero passwords to memorize. Pay the fixed fee on demand, put in your email, and you&apos;re good to go.
          </p>
        </div>

        {/* The Checkout Card */}
        <OnDemandCheckoutCard onUnlocked={handleUnlocked} />

        {/* Security and Admin Link Footer */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-slate-800/80 text-xs text-slate-400">
          <div className="flex items-center gap-1.5 text-slate-400">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span>Secure 256-Bit TLS • GCash / Maya / Card</span>
          </div>

          <Link
            href="/admin/login"
            className="text-slate-400 hover:text-white transition-colors underline underline-offset-4"
          >
            Operator Console Login →
          </Link>
        </div>
      </div>
    </div>
  );
}
