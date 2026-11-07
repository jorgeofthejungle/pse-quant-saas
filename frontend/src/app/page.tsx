'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
  ShieldCheck,
  Zap,
  Clock,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Sparkles,
  BarChart3,
  HeartHandshake,
} from 'lucide-react';
import ScreenerTable from '@/components/ScreenerTable';
import OnDemandCheckoutCard from '@/components/OnDemandCheckoutCard';
import { MOCK_RANKINGS } from '@/lib/mockData';

export default function HomePage() {
  const [teaserSeasoned, setTeaserSeasoned] = useState(false);

  return (
    <div className="flex flex-col gap-20 pb-20">
      {/* ── 1. Hero Section & PWYC Done-For-You Report Builder ──── */}
      <section className="relative overflow-hidden pt-16 pb-12 sm:pt-24">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(37,99,235,0.18),rgba(255,255,255,0))]" />

        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-500/10 px-3.5 py-1 text-xs font-semibold text-blue-400 mb-6">
            <span className="flex h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
            Outcome as a Service • Pay What You Can (PWYC) Per Report • Zero Subscriptions
          </div>

          <h1 className="mx-auto max-w-4xl text-4xl font-extrabold tracking-tight text-white sm:text-6xl sm:leading-tight">
            Done-For-You PSE Research.{' '}
            <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-amber-300 bg-clip-text text-transparent">
              Just Take Your Pick.
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base sm:text-lg text-slate-400 leading-relaxed">
            Pagod ka na bang magtanong sa FB groups ng{' '}
            <span className="italic text-slate-200">&ldquo;Ano po maganda bilhin?&rdquo;</span> at sumunod sa blind hype?
            Sinusuri ng algorithm namin ang 250+ PSE stocks at binibigyan ka ng malinaw na{' '}
            <strong className="text-white">Fact Card</strong> + <strong className="text-white">Seasoned Numbers</strong>.
            Pay What You Can per report—walang monthly subscription.
          </p>

          {/* ── Main PWYC Report Checkout Card ───────────────── */}
          <div className="mt-10 mx-auto max-w-2xl text-left">
            <OnDemandCheckoutCard />
          </div>

          {/* Quick Stats Strip */}
          <div className="mt-12 grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-4xl mx-auto">
            <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 text-center">
              <span className="text-2xl font-bold text-white">250+</span>
              <p className="text-xs text-slate-400 mt-1">PSE Stocks Audited</p>
            </div>
            <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 text-center">
              <span className="text-2xl font-bold text-blue-400">PWYC</span>
              <p className="text-xs text-slate-400 mt-1">Pay What You Can (≥ ₱49)</p>
            </div>
            <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 text-center">
              <span className="text-2xl font-bold text-emerald-400">Fact Card</span>
              <p className="text-xs text-slate-400 mt-1">Taglish + Seasoned Toggle</p>
            </div>
            <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 text-center">
              <span className="text-2xl font-bold text-amber-400">Hype Check</span>
              <p className="text-xs text-slate-400 mt-1">Test Stocks Seen on FB</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── 2. Free Teaser Sample: Live Fact Card + Hype Check ── */}
      <section className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <div className="rounded-3xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-0.5 text-xs font-bold text-emerald-400 mb-2">
                <Sparkles className="h-3.5 w-3.5" />
                <span>Free Live Teaser Sample</span>
              </div>
              <h2 className="text-2xl font-extrabold text-white">
                Ganito Kalinaw ang Makikita Mo sa Report
              </h2>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                Sample ng isang <strong>Top Pick Fact Card</strong> at isang <strong>FB Group Hype Check</strong>. Pwede mo ring i-click ang Seasoned Numbers toggle.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setTeaserSeasoned(!teaserSeasoned)}
              className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition-all cursor-pointer ${
                teaserSeasoned
                  ? 'bg-blue-500 text-white shadow-md'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700'
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              {teaserSeasoned ? 'Hide Seasoned Numbers' : '+ Seasoned Numbers Toggle'}
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Sample 1: AREIT Top Pick */}
            <div className="rounded-2xl border border-emerald-500/30 bg-slate-950/70 p-5">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div>
                  <span className="text-lg font-extrabold text-white">AREIT</span>
                  <span className="text-xs text-slate-400 ml-2">AREIT, Inc.</span>
                </div>
                <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-[11px] font-bold text-emerald-300">
                  Option A: Steady Dividend Payer
                </span>
              </div>

              <div className="space-y-2 text-xs text-slate-300 bg-slate-900/70 rounded-xl p-3.5 border border-slate-800">
                <p>
                  <strong className="text-white">• Verdict:</strong> Solid pang-passive income ang AREIT: nagbibigay ng 6.44% net dividend yield habang naka-discount pa ng 22.1% sa Fair Value nito.
                </p>
                <p>
                  <strong className="text-emerald-400">• Peso Value Test:</strong> Nagbabayad ka lang ng ₱0.78 for every ₱1.00 of true business value (Current Price: ₱36.50 vs. Fair Value: ₱46.84 — 22.1% discount).
                </p>
                <p>
                  <strong className="text-amber-400">• Net Dividend per ₱10k:</strong> Sa bawat ₱10,000 na investment, kikita ka ng ~₱644/year in net cash dividends (6.44% net after 10% tax) — halos 26x na mas mataas kaysa sa 0.25% traditional bank savings.
                </p>
                <p>
                  <strong className="text-blue-400">• Health:</strong> Quality Score: 73.0/100. Kumikita ng ₱12.8 net profit sa bawat ₱100 na capital (ROE). Mababa at safe ang utang (₱36 debt per ₱100 equity).
                </p>
              </div>

              {teaserSeasoned && (
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs bg-slate-900 rounded-xl p-3 border border-blue-500/20">
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">3-Layer Score</span>
                    <span className="font-bold text-white">73.0/100 (H:78.5 I:69.0 P:71.5)</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">DCF/DDM Fair Value</span>
                    <span className="font-bold text-emerald-400">₱46.84 (+22.1% MoS)</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Net Yield vs BVAL</span>
                    <span className="font-bold text-amber-300">6.44% (+59 bps vs 10Y)</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">ROE & Debt/Equity</span>
                    <span className="font-bold text-slate-200">ROE 12.8% • D/E 0.36x</span>
                  </div>
                </div>
              )}
            </div>

            {/* Sample 2: DITO Hype Check */}
            <div className="rounded-2xl border border-rose-500/30 bg-slate-950/70 p-5">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div>
                  <span className="text-lg font-extrabold text-white">DITO</span>
                  <span className="text-xs text-slate-400 ml-2">DITO CME Holdings</span>
                </div>
                <span className="rounded-full bg-rose-500/20 border border-rose-500/30 px-2.5 py-0.5 text-[11px] font-bold text-rose-300">
                  Hype Trap / Avoid For Now
                </span>
              </div>

              <div className="space-y-2 text-xs text-slate-300 bg-slate-900/70 rounded-xl p-3.5 border border-slate-800">
                <p>
                  <strong className="text-white">• Verdict:</strong> Iwas muna sa DITO: bagsak sa safety at valuation filter natin (Score: 28.5/100). Huwag basta maniwala sa FB group hype hangga&apos;t hindi umaayos ang kita at presyo.
                </p>
                <p>
                  <strong className="text-emerald-400">• Peso Value Test:</strong> Mas mahal na sa Fair Value ngayon: nagbabayad ka ng ₱2.20 for every ₱1.00 of value (Current Price: ₱1.65 vs. Fair Value: ₱0.75).
                </p>
                <p>
                  <strong className="text-amber-400">• Net Dividend per ₱10k:</strong> ₱0/year sa ngayon — walang cash dividend payout.
                </p>
                <p>
                  <strong className="text-blue-400">• Health:</strong> Quality Score: 28.5/100. Nalulugi ng ₱18.5 sa bawat ₱100 na capital (-18.5% ROE) at mataas ang utang (₱420 debt per ₱100 equity).
                </p>
              </div>

              {teaserSeasoned && (
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs bg-slate-900 rounded-xl p-3 border border-blue-500/20">
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">3-Layer Score</span>
                    <span className="font-bold text-rose-400">28.5/100 (H:22.0 I:33.0 P:30.5)</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">DCF/DDM Fair Value</span>
                    <span className="font-bold text-rose-400">₱0.75 (-120% MoS)</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Net Yield</span>
                    <span className="font-bold text-slate-400">0.00%</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">ROE & Debt/Equity</span>
                    <span className="font-bold text-rose-300">ROE -18.5% • D/E 4.20x</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── 3. Comparison: FB Hype & Subscriptions vs Done-For-You PWYC ── */}
      <section className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-xs font-bold uppercase tracking-wider text-blue-400">Why We Built This</h2>
          <p className="mt-2 text-3xl font-extrabold tracking-tight text-white">
            Tapusin Na ang Panghuhula sa Stock Market
          </p>
          <p className="mt-3 text-slate-400 text-sm max-w-xl mx-auto">
            Hindi mo kailangan magbayad ng mahal na monthly subscription o umasa sa hula ng strangers sa social media.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Old Way Card */}
          <div className="rounded-3xl border border-rose-900/40 bg-gradient-to-b from-rose-950/20 to-slate-900/50 p-7 backdrop-blur-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20">
                <XCircle className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">FB Group Hype &amp; Monthly SaaS</h3>
                <span className="text-xs font-semibold text-rose-400">Nakakalito at Magastos</span>
              </div>
            </div>

            <ul className="space-y-4 text-sm text-slate-400">
              <li className="flex items-start gap-3">
                <XCircle className="h-4 w-4 text-rose-500 shrink-0 mt-0.5" />
                <span>
                  <strong>Blind advice sa FB groups:</strong> Nagtatanong ng <em>&ldquo;Ano po maganda bilhin?&rdquo;</em> at naiipit sa hyped na bodega stocks.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <XCircle className="h-4 w-4 text-rose-500 shrink-0 mt-0.5" />
                <span>
                  <strong>Nakakalula ang jargon:</strong> Puro acronyms (`ROE`, `EV/EBITDA`, `DCF`) na walang paliwanag kung ano ang ibig sabihin sa pera mo.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <XCircle className="h-4 w-4 text-rose-500 shrink-0 mt-0.5" />
                <span>
                  <strong>Mahal na monthly subscriptions:</strong> ₱999–₱1,500/month kahit isang beses sa isang buwan ka lang naman bumibili ng stocks.
                </span>
              </li>
            </ul>
          </div>

          {/* Outcome as a Service Card */}
          <div className="rounded-3xl border border-emerald-500/40 bg-gradient-to-b from-emerald-950/30 to-slate-900/70 p-7 backdrop-blur-sm shadow-xl shadow-emerald-950/20">
            <div className="flex items-center gap-3 mb-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                <CheckCircle2 className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">StockPilot Done-For-You OaaS</h3>
                <span className="text-xs font-semibold text-emerald-400">Malinaw na Facts • Pay What You Can</span>
              </div>
            </div>

            <ul className="space-y-4 text-sm text-slate-300">
              <li className="flex items-start gap-3">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Done-For-You Menu (&ldquo;Take Your Pick&rdquo;):</strong> Pinili na ng algorithm ang top Dividend, Undervalued, at Growth stocks para pipili ka na lang.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>
                  <strong>4-Part Taglish Fact Card + Seasoned Numbers:</strong> Malinaw na Verdict, Peso Value Test, Net Dividend per ₱10k, at Health.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Pay What You Can (PWYC) per report:</strong> Abot-kaya para sa nagsisimula (₱99 Starter), habang pwedeng mag-Pay-It-Forward ang seasoned investors.
                </span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* ── 4. The 3-Layer Fundamental Model ─────────────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-xs font-bold uppercase tracking-wider text-blue-400">Paano Gumagana ang Algorithm</h2>
          <p className="mt-2 text-3xl font-extrabold tracking-tight text-white">
            3-Layer Fundamental &amp; Valuation Audit
          </p>
          <p className="mt-3 text-slate-400 text-sm max-w-xl mx-auto">
            Walang hula at walang chismis. Bawat stock sa report ay dumaan sa tatlong patong ng mathematical audit.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 mb-4 border border-emerald-500/20">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Layer 1: Financial Health</h3>
            <span className="text-xs font-semibold text-emerald-400">Kumikita ba at Safe sa Utang?</span>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Sinusuri ang ROE, net profit margin, debt-to-equity ratio, at free cash flow para siguraduhing matatag ang pundasyon ng kumpanya.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400 mb-4 border border-blue-500/20">
              <Zap className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Layer 2: Improvement</h3>
            <span className="text-xs font-semibold text-blue-400">Umaangat ba ang Kita Year-over-Year?</span>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Tinitingnan ang 3-year trend ng revenue, earnings per share (EPS), at dividend payouts para makita kung lumalakas ang negosyo.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-sm">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 mb-4 border border-amber-500/20">
              <Clock className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Layer 3: Persistence &amp; Fair Value</h3>
            <span className="text-xs font-semibold text-amber-400">Sulit ba ang Presyo Ngayon?</span>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Kinukwenta ang tunay na halaga (Intrinsic Fair Value via DCF &amp; DDM) para malaman kung naka-sale ang stock o overpriced na.
            </p>
          </div>
        </div>
      </section>

      {/* ── 5. Live Market Leaderboard Preview ───────────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400 mb-2">
              <Sparkles className="h-3.5 w-3.5" />
              <span>Full Market Screener Preview</span>
            </div>
            <h2 className="text-2xl font-extrabold text-white">Top Scored Philippine Equities</h2>
            <p className="text-sm text-slate-400 mt-1">
              Kapag nag-request ka ng report sa itaas, automatic ding naka-unlock ang buong 250+ stock screener at DCF Margin of Safety numbers.
            </p>
          </div>

          <Link
            href="/screener"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-400 hover:text-blue-300"
          >
            <span>Explore Full Screener</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        <ScreenerTable initialStocks={MOCK_RANKINGS} />
      </section>

      {/* ── 6. Bottom CTA ────────────────────────────────────── */}
      <section className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-blue-500/30 bg-gradient-to-b from-slate-900 via-slate-950 to-blue-950/40 p-8 sm:p-12 text-center shadow-2xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/20 bg-amber-500/10 px-3.5 py-1 text-xs font-semibold text-amber-400 mb-4">
            <HeartHandshake className="h-3.5 w-3.5" />
            <span>Pay What You Can • Walang Subscription</span>
          </div>

          <h2 className="text-3xl font-extrabold text-white sm:text-4xl">
            Handa ka na bang pumili ng tamang stocks?
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-sm text-slate-400 leading-relaxed">
            Piliin ang goal mo, i-check ang stock na nakita mo sa FB, at kunin ang iyong Done-For-You Report + A4 PDF Dossier.
          </p>

          <div className="mt-8 flex justify-center">
            <a
              href="#top"
              onClick={(e) => {
                e.preventDefault();
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-8 py-3.5 text-sm font-bold text-white shadow-lg shadow-blue-500/25 transition-all hover:brightness-110 cursor-pointer"
            >
              <span>Request My Done-For-You Report</span>
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
