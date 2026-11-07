'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  ShieldCheck,
  CheckCircle2,
  Download,
  ArrowRight,
  Zap,
  Mail,
  Lock,
  RefreshCw,
  AlertCircle,
  HeartHandshake,
  Coins,
  BookOpen,
  BarChart3,
  Search,
} from 'lucide-react';
import { outcomeApi, OutcomeAccess } from '@/lib/api';

interface OnDemandCheckoutCardProps {
  className?: string;
  defaultEmail?: string;
  onUnlocked?: (email: string) => void;
}

const PWYC_PRESETS = [
  {
    id: 'starter',
    amount: 99,
    title: 'Starter / Studyante',
    badge: 'Accessible Floor',
    desc: 'Pang-nagsisimula pa lang. Covers our server & PSE data processing costs.',
  },
  {
    id: 'community',
    amount: 249,
    title: 'Fair Community Price',
    badge: 'Recommended',
    desc: 'Standard Done-For-You Report price. Keeps the platform sustainable for all Filipinos.',
  },
  {
    id: 'supporter',
    amount: 499,
    title: 'Seasoned / Pay-It-Forward',
    badge: 'Sponsors 2 Beginners',
    desc: 'Para sa seasoned investors. Directly sponsors research access for 2 beginners.',
  },
];

const GOAL_OPTIONS = [
  { id: 'all', label: 'All Top Picks (Complete Menu)' },
  { id: 'dividend', label: 'Option A: Steady Cash Dividends (REITs & Yield)' },
  { id: 'value', label: 'Option B: Undervalued Blue Chips (On-Sale)' },
  { id: 'growth', label: 'Option C: Quality Growth Compounders' },
];

const FALLBACK_OPTIONS = [
  {
    rank: 1,
    ticker: 'AREIT',
    name: 'AREIT, Inc.',
    sector: 'Property',
    bucket_tag: 'PASSIVE_INCOME_CHAMPION',
    bucket_label: 'Option A: Steady Dividend Payer',
    fact_card: {
      bucket_label: 'Option A: Steady Dividend Payer',
      verdict:
        'Solid pang-passive income ang AREIT, Inc. (AREIT): nagbibigay ng 6.44% net dividend yield habang naka-discount pa ng 22.1% sa Fair Value nito.',
      peso_value_test:
        'Nagbabayad ka lang ng ₱0.78 for every ₱1.00 of true business value (Current Price: ₱36.50 vs. Fair Value: ₱46.84 — 22.1% discount).',
      net_dividend_per_10k:
        'Sa bawat ₱10,000 na investment, kikita ka ng ~₱644/year in net cash dividends (6.44% net after 10% tax; 7.15% gross) — halos 26x na mas mataas kaysa sa 0.25% traditional bank savings account.',
      health:
        'Quality Score: 73.0/100 (Highest Quality). Kumikita ang negosyo ng ₱12.8 net profit sa bawat ₱100 na capital (ROE). Mababa at safe ang utang (₱36 debt per ₱100 equity).',
    },
    seasoned_numbers: {
      composite_score: 73.0,
      health_score: 78.5,
      improvement_score: 69.0,
      persistence_score: 71.5,
      current_price_php: 36.5,
      intrinsic_value_php: 46.84,
      margin_of_safety_pct: 22.1,
      net_dividend_yield_pct: 6.44,
      net_annual_cash_per_10k_php: 644,
      roe_pct: 12.8,
      debt_to_equity: 0.36,
    },
  },
  {
    rank: 2,
    ticker: 'DMC',
    name: 'DMCI Holdings, Inc.',
    sector: 'Holding Firms',
    bucket_tag: 'PASSIVE_INCOME_CHAMPION',
    bucket_label: 'Option A: Steady Dividend Payer',
    fact_card: {
      bucket_label: 'Option A: Steady Dividend Payer',
      verdict:
        'Solid pang-passive income ang DMCI Holdings, Inc. (DMC): nagbibigay ng 7.65% net dividend yield habang naka-discount pa ng 18.4% sa Fair Value nito.',
      peso_value_test:
        'Nagbabayad ka lang ng ₱0.82 for every ₱1.00 of true business value (Current Price: ₱12.40 vs. Fair Value: ₱15.20 — 18.4% discount).',
      net_dividend_per_10k:
        'Sa bawat ₱10,000 na investment, kikita ka ng ~₱765/year in net cash dividends (7.65% net after 10% tax; 8.50% gross) — halos 31x na mas mataas kaysa sa 0.25% traditional bank savings account.',
      health:
        'Quality Score: 68.5/100 (Highest Quality). Kumikita ang negosyo ng ₱19.4 net profit sa bawat ₱100 na capital (ROE). Mababa at safe ang utang (₱48 debt per ₱100 equity).',
    },
    seasoned_numbers: {
      composite_score: 68.5,
      health_score: 74.0,
      improvement_score: 63.0,
      persistence_score: 68.5,
      current_price_php: 12.4,
      intrinsic_value_php: 15.2,
      margin_of_safety_pct: 18.4,
      net_dividend_yield_pct: 7.65,
      net_annual_cash_per_10k_php: 765,
      roe_pct: 19.4,
      debt_to_equity: 0.48,
    },
  },
  {
    rank: 3,
    ticker: 'BDO',
    name: 'BDO Unibank, Inc.',
    sector: 'Banks',
    bucket_tag: 'UNDERVALUED_BLUE_CHIP',
    bucket_label: 'Option B: Undervalued Blue Chip',
    fact_card: {
      bucket_label: 'Option B: Undervalued Blue Chip',
      verdict:
        'On-sale na higante ang BDO Unibank, Inc. (BDO): matatag ang fundamentals (71.4/100) at may 18.4% Margin of Safety discount laban sa ₱182.00 Fair Value nito.',
      peso_value_test:
        'Nagbabayad ka lang ng ₱0.82 for every ₱1.00 of true business value (Current Price: ₱148.50 vs. Fair Value: ₱182.00 — 18.4% discount).',
      net_dividend_per_10k:
        'Sa bawat ₱10,000 na investment, kikita ka ng ~₱239/year in net cash dividends (2.39% net after 10% tax; 2.65% gross) — halos 10x na mas mataas kaysa sa 0.25% traditional bank savings account.',
      health:
        'Quality Score: 71.4/100 (Highest Quality). Kumikita ang negosyo ng ₱15.2 net profit sa bawat ₱100 na capital (ROE). Manageable ang utang (D/E ratio: 0.85x).',
    },
    seasoned_numbers: {
      composite_score: 71.4,
      health_score: 75.0,
      improvement_score: 70.2,
      persistence_score: 69.0,
      current_price_php: 148.5,
      intrinsic_value_php: 182.0,
      margin_of_safety_pct: 18.4,
      net_dividend_yield_pct: 2.39,
      net_annual_cash_per_10k_php: 239,
      roe_pct: 15.2,
      debt_to_equity: 0.85,
    },
  },
  {
    rank: 4,
    ticker: 'DITO',
    name: 'DITO CME Holdings Corp.',
    sector: 'Services',
    bucket_tag: 'VALUE_OR_HYPE_TRAP',
    bucket_label: 'Hype Trap / Avoid For Now',
    fact_card: {
      bucket_label: 'Hype Trap / Avoid For Now',
      verdict:
        'Iwas muna sa DITO CME Holdings Corp. (DITO): base sa audited PSE Edge financials, may ₱13.75 Billion net loss ito (EPS: ₱-0.63) at bagsak sa safety filter (persistent negative earnings; 3Y normalized EPS = -0.69).',
      peso_value_test:
        'Current Price is ₱0.55, pero walang DCF/EPS Fair Value cushion dahil negatibo ang kita (EPS: ₱-0.63) — mataas ang panganib ng dilution o capital loss.',
      net_dividend_per_10k:
        '₱0/year (0.00% dividend yield) — hindi makapagbigay ng cash dividend dahil nalulugi pa ang operasyon.',
      health:
        'Quality Score: 37.6/100 (Watchlist). Audited Net Loss: -₱13.75 Billion. Capital Deficiency (Negative Shareholder Equity: -₱42.27B; Total Liabilities: ₱306.21B).',
    },
    seasoned_numbers: {
      composite_score: 37.6,
      health_score: 5.0,
      improvement_score: 94.4,
      persistence_score: 82.7,
      current_price_php: 0.55,
      intrinsic_value_php: null,
      margin_of_safety_pct: null,
      net_dividend_yield_pct: 0.0,
      net_annual_cash_per_10k_php: 0,
      roe_pct: null,
      debt_to_equity: null,
    },
  },
];

export default function OnDemandCheckoutCard({
  className = '',
  defaultEmail = '',
  onUnlocked,
}: OnDemandCheckoutCardProps) {
  const [email, setEmail] = useState(defaultEmail);
  const [selectedPreset, setSelectedPreset] = useState<string>('community');
  const [amountPhp, setAmountPhp] = useState<number>(249);
  const [customAmountStr, setCustomAmountStr] = useState<string>('249');
  const [investorGoal, setInvestorGoal] = useState<string>('all');
  const [hypeTicker, setHypeTicker] = useState<string>('');
  const [paymentMethod, setPaymentMethod] = useState<'gcash' | 'maya' | 'card'>('gcash');
  const [mode, setMode] = useState<'checkout' | 'restore'>('checkout');
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [activeOutcome, setActiveOutcome] = useState<OutcomeAccess | null>(null);
  const [impactNote, setImpactNote] = useState<string | null>(null);
  const [menuData, setMenuData] = useState<any>(null);
  const [showSeasoned, setShowSeasoned] = useState<boolean>(false);

  useEffect(() => {
    const stored = outcomeApi.getStoredOutcome();
    if (stored && stored.unlocked) {
      setActiveOutcome(stored);
      if (onUnlocked) onUnlocked(stored.email);
      outcomeApi.getDoneForYouMenu(investorGoal, hypeTicker).then((d) => {
        if (d) setMenuData(d);
      });
    }
  }, [onUnlocked]);

  const handleSelectPreset = (id: string, amt: number) => {
    setSelectedPreset(id);
    setAmountPhp(amt);
    setCustomAmountStr(String(amt));
    setError(null);
  };

  const handleCustomAmountChange = (val: string) => {
    setSelectedPreset('custom');
    setCustomAmountStr(val);
    const parsed = parseFloat(val);
    if (!isNaN(parsed)) {
      setAmountPhp(parsed);
    }
  };

  const handleHypeSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const d = await outcomeApi.getDoneForYouMenu(investorGoal, hypeTicker);
    if (d) setMenuData(d);
  };

  const handleCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes('@') || !cleanEmail.includes('.')) {
      setError('Pakilagay ang valid email address mo.');
      return;
    }

    if (isNaN(amountPhp) || amountPhp < 49) {
      setError('Minimum Pay-What-You-Can contribution is ₱49 para ma-cover ang server & data costs.');
      return;
    }

    setLoading(true);
    setLoadingStep(`Processing ₱${amountPhp.toFixed(0)} PWYC pass...`);

    try {
      await new Promise((r) => setTimeout(r, 400));
      setLoadingStep('Generating Taglish Fact Cards & Seasoned Numbers...');
      await new Promise((r) => setTimeout(r, 400));
      setLoadingStep('Unlocking Done-For-You Menu & PDF Dossier...');

      const result = await outcomeApi.checkoutOnDemand(
        cleanEmail,
        paymentMethod,
        undefined,
        amountPhp,
        investorGoal,
        hypeTicker
      );
      setActiveOutcome({
        email: cleanEmail,
        unlocked: true,
        tier: 'paid',
        plan: 'on_demand',
        downloadUrl: result.download_url,
      });
      if (result.pwyc_impact_note) {
        setImpactNote(result.pwyc_impact_note);
      }

      const menu = await outcomeApi.getDoneForYouMenu(investorGoal, hypeTicker);
      if (menu) setMenuData(menu);

      if (onUnlocked) onUnlocked(cleanEmail);
    } catch (err: any) {
      setError(err.message || 'Nagka-problema sa pag-process. Pakisubukan ulit.');
    } finally {
      setLoading(false);
      setLoadingStep('');
    }
  };

  const handleRestore = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes('@')) {
      setError('Pakilagay ang valid email address mo.');
      return;
    }

    setLoading(true);
    try {
      const res = await outcomeApi.verifyAccess(cleanEmail);
      if (res.has_access) {
        const stored = outcomeApi.getStoredOutcome();
        setActiveOutcome(
          stored || {
            email: cleanEmail,
            unlocked: true,
            tier: 'paid',
            plan: 'on_demand',
            downloadUrl: outcomeApi.getDownloadUrl(),
          }
        );
        const menu = await outcomeApi.getDoneForYouMenu(investorGoal, hypeTicker);
        if (menu) setMenuData(menu);
        if (onUnlocked) onUnlocked(cleanEmail);
      } else {
        setError(res.message || 'Walang nakitang report record para sa email na ito.');
      }
    } catch {
      setError('Unable to verify access right now.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    outcomeApi.clearStoredOutcome();
    setActiveOutcome(null);
    setEmail('');
  };

  // Helper to render a single Fact Card + Seasoned Numbers toggle
  const renderFactCard = (opt: any, isHighlightedHype = false) => {
    const fc = opt.fact_card || opt.plain_facts || {};
    const sn = opt.seasoned_numbers || opt.forensic_proof || {};
    const isTrap = opt.bucket_tag === 'VALUE_OR_HYPE_TRAP';

    return (
      <div
        key={`${opt.ticker}-${isHighlightedHype ? 'hype' : 'menu'}`}
        className={`rounded-2xl border p-4 sm:p-5 transition-all ${
          isHighlightedHype
            ? 'border-amber-500/50 bg-amber-950/20 shadow-lg shadow-amber-950/20'
            : isTrap
            ? 'border-rose-500/30 bg-rose-950/20'
            : 'border-slate-800 bg-slate-900/75 hover:border-slate-700'
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
          <div className="flex items-center gap-2.5">
            {isHighlightedHype && (
              <span className="rounded-md bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-amber-300">
                PSE Edge Reality Check
              </span>
            )}
            <span className="text-lg font-extrabold text-white">{opt.ticker}</span>
            <span className="text-xs text-slate-400">{opt.name}</span>
          </div>
          <span
            className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
              isTrap
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                : 'bg-blue-500/15 text-blue-300 border border-blue-500/30'
            }`}
          >
            {fc.bucket_label || opt.bucket_label}
          </span>
        </div>

        {/* 4-Part Taglish Fact Card */}
        <div className="space-y-2 text-xs text-slate-300 bg-slate-950/65 rounded-xl p-3.5 border border-slate-800/80">
          <p>
            <strong className="text-white">• Verdict:</strong>{' '}
            <span className="text-slate-200">{fc.verdict || fc.headline_verdict}</span>
          </p>
          <p>
            <strong className="text-emerald-400">• Peso Value Test:</strong>{' '}
            <span>{fc.peso_value_test || fc.piso_value_fact}</span>
          </p>
          <p>
            <strong className="text-amber-400">• Net Dividend per ₱10k:</strong>{' '}
            <span>{fc.net_dividend_per_10k || fc.dividend_cash_fact}</span>
          </p>
          <p>
            <strong className="text-blue-400">• Health:</strong>{' '}
            <span>{fc.health || fc.business_safety_fact}</span>
          </p>
        </div>

        {/* Seasoned Numbers Toggle Output */}
        {showSeasoned && (
          <div className="mt-2.5 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs bg-slate-900/90 rounded-xl p-3 border border-blue-500/20">
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">3-Layer Score</span>
              <span className="font-bold text-white">
                {sn.composite_score}/100{' '}
                {sn.health_score ? `(H:${sn.health_score} I:${sn.improvement_score} P:${sn.persistence_score})` : ''}
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">Price vs Fair Value</span>
              <span className="font-bold text-emerald-400">
                ₱{sn.current_price_php} / ₱{sn.intrinsic_value_php ?? 'N/A'} ({sn.margin_of_safety_pct ?? 0}% MoS)
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">Net Div (After 10% Tax)</span>
              <span className="font-bold text-amber-300">
                {sn.net_dividend_yield_pct}% (₱{sn.net_annual_cash_per_10k_php}/10k)
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">ROE & Debt/Equity</span>
              <span className="font-bold text-slate-200">
                ROE {sn.roe_pct ?? 'N/A'}% • D/E {sn.debt_to_equity ?? 'N/A'}x
              </span>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── 1. UNLOCKED STATE: DONE-FOR-YOU INVESTMENT MENU ("TAKE YOUR PICK") ──
  if (activeOutcome && activeOutcome.unlocked) {
    const options = menuData?.options?.length ? menuData.options : FALLBACK_OPTIONS;
    const hypeResult =
      menuData?.hype_check_result ||
      (hypeTicker.trim()
        ? options.find((o: any) => o.ticker === hypeTicker.trim().toUpperCase())
        : null);

    return (
      <div
        className={`relative overflow-hidden rounded-3xl border border-emerald-500/40 bg-gradient-to-b from-emerald-950/30 via-slate-900/95 to-slate-950 p-6 sm:p-8 shadow-2xl shadow-emerald-950/30 ${className}`}
      >
        <div className="relative z-10">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-3.5 py-1 text-xs font-bold text-emerald-300">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              Done-For-You Report Unlocked • Zero Subscription
            </div>
            <button
              onClick={handleReset}
              className="text-xs text-slate-400 hover:text-slate-200 underline transition-colors"
            >
              Request New Report / Switch Email
            </button>
          </div>

          <h3 className="text-2xl font-extrabold text-white tracking-tight">
            Done-For-You Investment Menu (&ldquo;Take Your Pick&rdquo;)
          </h3>
          <p className="mt-1 text-xs sm:text-sm text-slate-300">
            Prepared for <span className="font-semibold text-emerald-300">{activeOutcome.email}</span>. Lahat ng options sa ibaba ay dumaan sa algorithm natin at may malinaw na <strong>Fact Card</strong>.
          </p>

          {impactNote && (
            <div className="mt-3 flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2 text-xs text-amber-300">
              <HeartHandshake className="h-4 w-4 shrink-0 text-amber-400" />
              <span>{impactNote}</span>
            </div>
          )}

          {/* Interactive Stock Reality Check Search Bar */}
          <form onSubmit={handleHypeSearch} className="mt-5 flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={hypeTicker}
                onChange={(e) => setHypeTicker(e.target.value.toUpperCase())}
                placeholder="Stock Reality Check (PSE Edge Data): Type any ticker (e.g. DITO, CEB, TEL, JFC, SM)..."
                className="w-full rounded-xl border border-slate-700/80 bg-slate-950/90 pl-10 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:border-amber-400 focus:outline-none"
              />
            </div>
            <button
              type="submit"
              className="rounded-xl bg-amber-500/20 border border-amber-500/40 px-4 py-2 text-xs font-bold text-amber-300 hover:bg-amber-500/30 transition-all cursor-pointer"
            >
              Audit Stock
            </button>
          </form>

          {/* Controls: Seasoned Numbers Toggle + PDF Download */}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <button
              type="button"
              onClick={() => setShowSeasoned(!showSeasoned)}
              className={`inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-bold transition-all cursor-pointer ${
                showSeasoned
                  ? 'bg-blue-500 text-white shadow-md'
                  : 'bg-slate-800/90 text-slate-300 hover:bg-slate-800'
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              {showSeasoned ? 'Hide Seasoned Numbers' : '+ Show Seasoned Numbers Toggle'}
            </button>

            <a
              href={outcomeApi.getDownloadUrl(investorGoal, hypeTicker)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-500/20 border border-emerald-500/40 px-4 py-2 text-xs font-bold text-emerald-300 hover:bg-emerald-500/30 transition-all"
            >
              <Download className="h-3.5 w-3.5" />
              Download Full A4 PDF Report
            </a>
          </div>

          {/* Highlighted Hype Check Result if queried */}
          {hypeResult && (
            <div className="mt-4">
              {renderFactCard(hypeResult, true)}
            </div>
          )}

          {/* Curated Stock Fact Cards */}
          <div className="mt-4 space-y-4">
            {options.slice(0, 4).map((opt: any) => renderFactCard(opt, false))}
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-800/80">
            <Link
              href="/screener"
              className="inline-flex items-center gap-2 text-xs font-bold text-blue-400 hover:text-blue-300"
            >
              Explore Full 250+ Stock Screener
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <span className="text-[11px] text-slate-500">
              Fact-Backed Quantitative Research • Not Broker-Affiliated
            </span>
          </div>
        </div>
      </div>
    );
  }

  // ── 2. CHECKOUT STATE: PAY-WHAT-YOU-CAN (PWYC) PER REPORT ────────────────
  return (
    <div
      className={`relative overflow-hidden rounded-3xl border border-blue-500/30 bg-gradient-to-b from-slate-900/95 via-slate-900/90 to-slate-950 p-6 sm:p-8 shadow-2xl shadow-blue-950/20 ${className}`}
    >
      <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-blue-500/10 blur-3xl pointer-events-none" />

      <div className="relative z-10">
        {/* Top Header */}
        <div className="flex flex-wrap items-center justify-between gap-2 mb-5">
          <div className="inline-flex items-center gap-2 rounded-full bg-blue-500/10 border border-blue-500/20 px-3 py-1 text-xs font-semibold text-blue-400">
            <HeartHandshake className="h-3.5 w-3.5 text-amber-400" />
            Pay What You Can (PWYC) • Per Report • No Subscriptions
          </div>

          <button
            type="button"
            onClick={() => {
              setMode(mode === 'checkout' ? 'restore' : 'checkout');
              setError(null);
            }}
            className="text-xs font-medium text-slate-400 hover:text-blue-400 transition-colors"
          >
            {mode === 'checkout' ? 'May report ka na dati? Restore here' : '← Back to Request Report'}
          </button>
        </div>

        {mode === 'checkout' ? (
          <form onSubmit={handleCheckout} className="space-y-5">
            <div>
              <h3 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight">
                Done-For-You Research: &ldquo;Ano Po Maganda Bilhin?&rdquo;
              </h3>
              <p className="mt-1 text-xs sm:text-sm text-slate-400">
                Huwag nang manghula o basta sumunod sa hype sa FB groups. Piliin ang goal mo at bibigyan ka namin ng curated options na may malinaw na <strong>Fact Card</strong> + <strong>Seasoned Numbers</strong>.
              </p>
            </div>

            {/* Step 1: Investor Goal & Optional FB Stock Hype Check */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                  1. Anong Goal Mo sa Pag-Invest?
                </label>
                <select
                  value={investorGoal}
                  onChange={(e) => setInvestorGoal(e.target.value)}
                  className="w-full rounded-xl border border-slate-700/80 bg-slate-950/90 px-3 py-2.5 text-xs text-white focus:border-blue-500 focus:outline-none"
                >
                  {GOAL_OPTIONS.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                  2. Stock Reality Check (Test Any PSE Ticker)
                </label>
                <input
                  type="text"
                  value={hypeTicker}
                  onChange={(e) => setHypeTicker(e.target.value.toUpperCase())}
                  placeholder="e.g. DITO, CEB, TEL, JFC, SM (Audited via PSE Edge)"
                  className="w-full rounded-xl border border-slate-700/80 bg-slate-950/90 px-3 py-2.5 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Step 2: Pay What You Can (PWYC) Tier Selector */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  3. Pay What You Can (Per Report — Walang Monthly Lock-In)
                </label>
                <span className="text-[11px] text-emerald-400 font-medium">Minimum ₱49 floor</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {PWYC_PRESETS.map((tier) => {
                  const active = selectedPreset === tier.id;
                  return (
                    <button
                      key={tier.id}
                      type="button"
                      onClick={() => handleSelectPreset(tier.id, tier.amount)}
                      className={`flex flex-col justify-between rounded-2xl border p-3 text-left transition-all cursor-pointer ${
                        active
                          ? 'border-blue-500 bg-blue-500/15 shadow-lg shadow-blue-500/10'
                          : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-1">
                          <span className="text-lg font-extrabold text-white">₱{tier.amount}</span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                              active ? 'bg-blue-500 text-white' : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {tier.badge}
                          </span>
                        </div>
                        <p className="text-xs font-bold text-slate-200 mt-1">{tier.title}</p>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1.5 leading-snug">{tier.desc}</p>
                    </button>
                  );
                })}
              </div>

              {/* Custom Amount Input */}
              <div className="mt-2.5 flex items-center gap-3 rounded-xl border border-slate-800/90 bg-slate-950/60 px-3.5 py-2">
                <Coins className="h-4 w-4 text-amber-400 shrink-0" />
                <span className="text-xs text-slate-300">Or enter custom PHP amount (≥ ₱49):</span>
                <div className="relative ml-auto w-28">
                  <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-400">
                    ₱
                  </span>
                  <input
                    type="number"
                    min={49}
                    max={100000}
                    value={customAmountStr}
                    onChange={(e) => handleCustomAmountChange(e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 pl-6 pr-2 py-1 text-right text-xs font-bold text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Step 3: Email & Payment Method */}
            <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 pt-1">
              <div className="sm:col-span-7">
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                  4. Email Address (Saan Ise-Send ang Report)
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full rounded-xl border border-slate-700/80 bg-slate-950/90 pl-10 pr-3 py-2.5 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="sm:col-span-5">
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                  Payment Method
                </label>
                <div className="grid grid-cols-3 gap-1.5">
                  {(
                    [
                      { id: 'gcash', label: 'GCash' },
                      { id: 'maya', label: 'Maya' },
                      { id: 'card', label: 'Card' },
                    ] as const
                  ).map((pm) => (
                    <button
                      key={pm.id}
                      type="button"
                      onClick={() => setPaymentMethod(pm.id)}
                      className={`rounded-xl border py-2.5 text-xs font-bold transition-all cursor-pointer ${
                        paymentMethod === pm.id
                          ? 'border-blue-500 bg-blue-500/15 text-blue-300'
                          : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      {pm.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-300">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-60 px-6 py-3.5 text-sm font-bold text-white shadow-lg shadow-blue-600/25 transition-all cursor-pointer"
            >
              {loading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span>{loadingStep || 'Generating Your Report...'}</span>
                </>
              ) : (
                <>
                  <Zap className="h-4 w-4 text-amber-300" />
                  <span>
                    Get My Done-For-You Report (₱{isNaN(amountPhp) ? 249 : amountPhp.toFixed(0)})
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px] text-slate-400">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                Includes Top Picks Menu + FB Hype Check + A4 PDF
              </span>
              <span>One-time per report • Walang auto-debit</span>
            </div>
          </form>
        ) : (
          /* Restore Existing Pass Form */
          <form onSubmit={handleRestore} className="space-y-4">
            <div>
              <h3 className="text-lg font-bold text-white">Restore Your Report Access</h3>
              <p className="text-xs text-slate-400 mt-1">
                Ilagay ang email address na ginamit mo para mabuksan ulit ang Done-For-You Menu at PDF report mo.
              </p>
            </div>

            <div className="relative">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-xl border border-slate-700/80 bg-slate-950/90 pl-10 pr-4 py-3 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-300">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-slate-800 hover:bg-slate-700 px-5 py-3 text-sm font-bold text-white transition-all cursor-pointer"
            >
              {loading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span>Verifying...</span>
                </>
              ) : (
                <>
                  <Lock className="h-4 w-4 text-blue-400" />
                  <span>Restore My Report & Menu</span>
                </>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
