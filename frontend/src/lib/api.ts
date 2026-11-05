/**
 * frontend/src/lib/api.ts — Central API Client for StockPilot PH
 * Connects the Customer Dashboard and Admin Dashboard to the Python Backend Server.
 */

import { StockRanking, StockDetail, SectorGroup, QualityCategory } from '@/types/stock';
import { MOCK_RANKINGS, MOCK_STOCK_DETAILS } from './mockData';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

function mapScoringGroup(rawGroup: string | undefined, sector: string): SectorGroup {
  if (!rawGroup) {
    if (sector.includes('Hold')) return 'Conglomerate';
    if (sector.includes('Bank') || sector.includes('Fin')) return 'Bank';
    if (sector.includes('Prop')) return 'Property';
    if (sector.includes('Indus')) return 'Industrial';
    if (sector.includes('Serv')) return 'Services';
    if (sector.includes('Min')) return 'Mining & Oil';
    return 'General';
  }
  const g = rawGroup.toLowerCase();
  if (g.includes('reit')) return 'REIT';
  if (g.includes('bank')) return 'Bank';
  if (g.includes('holding') || g.includes('cong')) return 'Conglomerate';
  if (g.includes('prop')) return 'Property';
  if (g.includes('indus')) return 'Industrial';
  if (g.includes('min')) return 'Mining & Oil';
  if (g.includes('serv')) return 'Services';
  return 'General';
}

function transformRawStock(item: any): StockRanking {
  return {
    rank: item.rank || 0,
    ticker: item.ticker,
    name: item.name || item.ticker,
    sector: item.sector || 'General',
    scoringGroup: mapScoringGroup(item.scoring_group, item.sector || ''),
    score: Number((item.score || 0).toFixed(1)),
    confidence: item.confidence ?? 1.0,
    category: (item.category || 'Watchlist') as QualityCategory,
    currentPrice: item.current_price || 0,
    intrinsicValue: item.intrinsic_value ?? null,
    mosPct: item.mos_pct ?? null,
    dividendYield: item.dividend_yield ?? null,
    pe: item.pe ?? null,
    pb: item.pb ?? null,
    roe: item.roe ?? null,
    deRatio: item.de_ratio ?? null,
  };
}

// ── Stock API ────────────────────────────────────────────────

export const stockApi = {
  async getRankings(portfolio = 'unified', sector?: string): Promise<StockRanking[]> {
    try {
      const url = new URL(`${BASE_URL}/stocks`);
      url.searchParams.set('portfolio', portfolio);
      if (sector) url.searchParams.set('sector', sector);

      const res = await fetch(url.toString(), { next: { revalidate: 60 } });
      if (res.ok) {
        const json = await res.json();
        if (json.data && json.data.length > 0) {
          return json.data.map(transformRawStock);
        }
      }
    } catch (err) {
      console.warn('[stockApi.getRankings] Server connection failed, falling back to benchmarks:', err);
    }
    return MOCK_RANKINGS;
  },

  async getProfile(ticker: string): Promise<StockDetail | null> {
    const cleanTicker = ticker.toUpperCase().trim();
    try {
      const res = await fetch(`${BASE_URL}/stocks/${cleanTicker}`, { next: { revalidate: 60 } });
      if (res.ok) {
        const data = await res.json();
        const ranking = transformRawStock(data);
        const val = data.valuation || {};
        const layers = data.layers || {};

        return {
          ...ranking,
          marketCap: data.market_cap || 0,
          dpsLast: data.dps_last ?? null,
          dividendCagr5y: data.dividend_cagr_5y ?? null,
          fcfPerShare: data.fcf_per_share ?? null,
          revenueCagr: data.revenue_cagr ?? null,
          requiredReturn: data.required_return || 0.125,
          layers: {
            health: {
              score: layers.health?.score || 0,
              weight: 0.35,
              factors: layers.health?.factors || {},
            },
            improvement: {
              score: layers.improvement?.score || 0,
              weight: 0.35,
              factors: layers.improvement?.factors || {},
            },
            persistence: {
              score: layers.persistence?.score || 0,
              weight: 0.30,
              factors: layers.persistence?.factors || {},
            },
          },
          valuation: {
            ddm: {
              value: val.ddm?.value ?? null,
              status: val.ddm?.status || 'DDM model applied',
            },
            epsPe: {
              value: val.eps_pe?.value ?? null,
              status: val.eps_pe?.status || 'EPS-PE multiple applied',
            },
            dcf: {
              value: val.dcf?.value ?? null,
              status: val.dcf?.status || 'DCF 10-year model applied',
            },
            conglomerateDiscountApplied: Boolean(val.conglomerate_discount_applied),
          },
          historicalFinancials: (data.historical_financials || []).map((f: any) => ({
            year: f.year,
            revenue: f.revenue || 0,
            netIncome: f.net_income || 0,
            equity: f.equity || 0,
            eps: f.eps || 0,
            dps: f.dps ?? null,
          })),
        };
      }
    } catch (err) {
      console.warn(`[stockApi.getProfile] Server error for ${cleanTicker}:`, err);
    }
    return MOCK_STOCK_DETAILS[cleanTicker] || null;
  },

  async getBargains(minMos = 0.0): Promise<StockRanking[]> {
    try {
      const res = await fetch(`${BASE_URL}/stocks/bargains?min_mos=${minMos}`, { cache: 'no-store' });
      if (res.ok) {
        const json = await res.json();
        return (json.data || []).map(transformRawStock);
      }
    } catch (err) {
      console.warn('[stockApi.getBargains] Error:', err);
    }
    return MOCK_RANKINGS.filter((s) => s.mosPct !== null && s.mosPct >= minMos);
  },

  async getMacro() {
    try {
      const res = await fetch(`${BASE_URL}/stocks/macro`, { next: { revalidate: 3600 } });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('[stockApi.getMacro] Error:', err);
    }
    return {
      ph_10y_bond_rate: 6.5,
      equity_risk_premium: 5.0,
      base_required_return: 11.5,
      conglomerate_holding_discount: 20.0,
      special_dividend_cap: 20.0,
    };
  },
};

// ── Customer API ─────────────────────────────────────────────

export interface CustomerProfile {
  id: number;
  email: string;
  name?: string;
  tier: string;
  status: string;
  notification_prefs?: { weekly_report: boolean; daily_brief: boolean; price_alerts: boolean };
  created_at: string;
}

export interface WatchlistItem {
  ticker: string;
  name: string;
  sector: string;
  current_price: number | null;
  intrinsic_value: number | null;
  current_mos_pct: number | null;
  target_mos_pct: number;
  is_triggered: boolean;
  notes?: string;
  added_at: string;
}

export const customerApi = {
  async signup(email: string, name?: string, tier = 'free'): Promise<CustomerProfile | null> {
    try {
      const res = await fetch(`${BASE_URL}/customers/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name, tier }),
      });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[customerApi.signup] Error:', err);
    }
    return null;
  },

  async getProfile(identifier: string): Promise<CustomerProfile | null> {
    try {
      const res = await fetch(`${BASE_URL}/customers/${identifier}`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[customerApi.getProfile] Error:', err);
    }
    return null;
  },

  async getWatchlist(userId: number): Promise<WatchlistItem[]> {
    try {
      const res = await fetch(`${BASE_URL}/customers/${userId}/watchlist`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[customerApi.getWatchlist] Error:', err);
    }
    return [];
  },

  async addToWatchlist(userId: number, ticker: string, targetMos = 20.0, notes?: string) {
    try {
      const res = await fetch(`${BASE_URL}/customers/${userId}/watchlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: ticker.toUpperCase(), target_mos_pct: targetMos, notes }),
      });
      return res.ok;
    } catch (err) {
      console.error('[customerApi.addToWatchlist] Error:', err);
      return false;
    }
  },

  async removeFromWatchlist(userId: number, ticker: string) {
    try {
      const res = await fetch(`${BASE_URL}/customers/${userId}/watchlist/${ticker.toUpperCase()}`, {
        method: 'DELETE',
      });
      return res.ok;
    } catch (err) {
      console.error('[customerApi.removeFromWatchlist] Error:', err);
      return false;
    }
  },
};

// ── Admin API ────────────────────────────────────────────────

export interface AdminMetrics {
  total_customers: number;
  paid_subscribers: number;
  free_members: number;
  mrr_php: number;
  active_watchlists: number;
  total_emails_delivered: number;
}

export interface PipelineRunLog {
  id: number;
  run_type: string;
  status: string;
  summary: any;
  error_message?: string;
  started_at: string;
  completed_at?: string;
}

export const adminApi = {
  async getMetrics(): Promise<AdminMetrics> {
    try {
      const res = await fetch(`${BASE_URL}/admin/metrics`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[adminApi.getMetrics] Error:', err);
    }
    return {
      total_customers: 0,
      paid_subscribers: 0,
      free_members: 0,
      mrr_php: 0,
      active_watchlists: 0,
      total_emails_delivered: 0,
    };
  },

  async listCustomers(skip = 0, limit = 50) {
    try {
      const res = await fetch(`${BASE_URL}/admin/customers?skip=${skip}&limit=${limit}`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[adminApi.listCustomers] Error:', err);
    }
    return [];
  },

  async getPipelineRuns(limit = 15): Promise<PipelineRunLog[]> {
    try {
      const res = await fetch(`${BASE_URL}/admin/pipeline/runs?limit=${limit}`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[adminApi.getPipelineRuns] Error:', err);
    }
    return [];
  },

  async triggerFullPipeline(tickers?: string[]) {
    const url = new URL(`${BASE_URL}/admin/pipeline/sync-all`);
    if (tickers && tickers.length > 0) {
      tickers.forEach((t) => url.searchParams.append('tickers', t));
    }
    const res = await fetch(url.toString(), { method: 'POST' });
    return await res.json();
  },

  async triggerQuoteScrape(tickers?: string[]) {
    const url = new URL(`${BASE_URL}/admin/pipeline/scrape-quotes`);
    if (tickers && tickers.length > 0) {
      tickers.forEach((t) => url.searchParams.append('tickers', t));
    }
    const res = await fetch(url.toString(), { method: 'POST' });
    return await res.json();
  },

  async triggerRecomputeScores() {
    const res = await fetch(`${BASE_URL}/admin/pipeline/score`, { method: 'POST' });
    return await res.json();
  },

  async triggerEmailDigest(recipients?: string[]) {
    const url = new URL(`${BASE_URL}/admin/pipeline/email-digest`);
    if (recipients && recipients.length > 0) {
      recipients.forEach((r) => url.searchParams.append('recipients', r));
    }
    const res = await fetch(url.toString(), { method: 'POST' });
    return await res.json();
  },

  async triggerEvaluateAlerts() {
    const res = await fetch(`${BASE_URL}/admin/pipeline/evaluate-alerts`, { method: 'POST' });
    return await res.json();
  },

  async overrideFinancials(ticker: string, year: number, data: any) {
    const res = await fetch(`${BASE_URL}/admin/stocks/${ticker.toUpperCase()}/financials/${year}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return await res.json();
  },
};
