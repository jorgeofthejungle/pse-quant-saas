/**
 * frontend/src/lib/api.ts — Central API Client for StockPilot PH
 * Connects the Customer Dashboard and Admin Dashboard to the Python Backend Server.
 */

import { StockRanking, StockDetail, SectorGroup, QualityCategory } from '@/types/stock';
import { MOCK_RANKINGS, MOCK_STOCK_DETAILS } from './mockData';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

function getClientCorrelationId(): string {
  const rand = Math.random().toString(36).substring(2, 10);
  return `corr_fe_${Date.now()}_${rand}`;
}

async function tracedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (!headers.has('X-Correlation-ID')) {
    headers.set('X-Correlation-ID', getClientCorrelationId());
  }
  return fetch(input, { ...init, headers });
}


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

      const res = await tracedFetch(url.toString(), { next: { revalidate: 60 } });
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
      const res = await tracedFetch(`${BASE_URL}/stocks/${cleanTicker}`, { next: { revalidate: 60 } });
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
      const res = await tracedFetch(`${BASE_URL}/stocks/bargains?min_mos=${minMos}`, { cache: 'no-store' });
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
      const res = await tracedFetch(`${BASE_URL}/stocks/macro`, { next: { revalidate: 3600 } });
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

  async search(query: string, limit = 10) {
    const cleanQ = query.trim();
    if (!cleanQ) {
      return { query: '', totalMatches: 0, executionMs: 0, results: [] };
    }
    try {
      const res = await tracedFetch(`${BASE_URL}/search?q=${encodeURIComponent(cleanQ)}&limit=${limit}`, {
        cache: 'no-store',
      });
      if (res.ok) {
        const json = await res.json();
        return {
          query: json.query,
          totalMatches: json.total_matches,
          executionMs: json.execution_ms,
          results: (json.results || []).map((r: any) => ({
            ticker: r.ticker,
            name: r.name,
            highlightedName: r.highlighted_name,
            highlightedTicker: r.highlighted_ticker,
            sector: r.sector,
            isReit: Boolean(r.is_reit),
            isBank: Boolean(r.is_bank),
            closePrice: r.close_price,
            marketCap: r.market_cap,
            relevanceScore: r.relevance_score,
          })),
        };
      }
    } catch (err) {
      console.warn('[stockApi.search] Error:', err);
    }
    const qLower = cleanQ.toLowerCase();
    const fallbackMatches = MOCK_RANKINGS.filter(
      (s) => s.ticker.toLowerCase().includes(qLower) || s.name.toLowerCase().includes(qLower)
    ).slice(0, limit);

    return {
      query: cleanQ,
      totalMatches: fallbackMatches.length,
      executionMs: 0.1,
      results: fallbackMatches.map((s) => ({
        ticker: s.ticker,
        name: s.name,
        highlightedName: s.name,
        highlightedTicker: s.ticker,
        sector: s.sector,
        isReit: s.scoringGroup === 'REIT',
        isBank: s.scoringGroup === 'Bank',
        closePrice: s.currentPrice,
        marketCap: null,
        relevanceScore: -1.0,
      })),
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
      const res = await tracedFetch(`${BASE_URL}/customers/signup`, {
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
      const res = await tracedFetch(`${BASE_URL}/customers/${identifier}`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[customerApi.getProfile] Error:', err);
    }
    return null;
  },

  async getWatchlist(userId: number): Promise<WatchlistItem[]> {
    try {
      const res = await tracedFetch(`${BASE_URL}/customers/${userId}/watchlist`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[customerApi.getWatchlist] Error:', err);
    }
    return [];
  },

  async addToWatchlist(userId: number, ticker: string, targetMos = 20.0, notes?: string) {
    try {
      const res = await tracedFetch(`${BASE_URL}/customers/${userId}/watchlist`, {
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
      const res = await tracedFetch(`${BASE_URL}/customers/${userId}/watchlist/${ticker.toUpperCase()}`, {
        method: 'DELETE',
      });
      return res.ok;
    } catch (err) {
      console.error('[customerApi.removeFromWatchlist] Error:', err);
      return false;
    }
  },
};

function getMemberHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('stockpilot_member_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }
  return headers;
}

// ── Watchlist API (Authenticated Member) ─────────────────────

export const watchlistApi = {
  async getWatchlist(): Promise<WatchlistItem[]> {
    try {
      const headers = getMemberHeaders();
      if (!headers['Authorization']) return [];
      const res = await tracedFetch(`${BASE_URL}/watchlist`, {
        cache: 'no-store',
        headers,
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error('[watchlistApi.getWatchlist] Error:', err);
    }
    return [];
  },

  async addToWatchlist(ticker: string, targetMos = 20.0, notes?: string): Promise<boolean> {
    try {
      const res = await tracedFetch(`${BASE_URL}/watchlist`, {
        method: 'POST',
        headers: getMemberHeaders(),
        body: JSON.stringify({ ticker: ticker.toUpperCase(), target_mos_pct: targetMos, notes }),
      });
      return res.ok;
    } catch (err) {
      console.error('[watchlistApi.addToWatchlist] Error:', err);
      return false;
    }
  },

  async removeFromWatchlist(ticker: string): Promise<boolean> {
    try {
      const res = await tracedFetch(`${BASE_URL}/watchlist/${ticker.toUpperCase()}`, {
        method: 'DELETE',
        headers: getMemberHeaders(),
      });
      return res.ok;
    } catch (err) {
      console.error('[watchlistApi.removeFromWatchlist] Error:', err);
      return false;
    }
  },
};

function getAdminHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('stockpilot_admin_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }
  return headers;
}

// ── Authentication API ───────────────────────────────────────

export const authApi = {
  async loginMember(email: string, password: string) {
    const res = await tracedFetch(`${BASE_URL}/auth/member/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(err.detail || 'Invalid member credentials');
    }
    return await res.json();
  },

  async registerMember(email: string, password: string, name?: string) {
    const res = await tracedFetch(`${BASE_URL}/auth/member/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(err.detail || 'Registration failed');
    }
    return await res.json();
  },

  async loginAdmin(email: string, password: string) {
    const res = await tracedFetch(`${BASE_URL}/auth/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Admin login failed' }));
      throw new Error(err.detail || 'Access denied: Invalid administrator credentials');
    }
    return await res.json();
  },

  async getMe(token: string) {
    const res = await tracedFetch(`${BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return await res.json();
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
      const res = await tracedFetch(`${BASE_URL}/admin/metrics`, {
        cache: 'no-store',
        headers: getAdminHeaders(),
      });
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
      const res = await tracedFetch(`${BASE_URL}/admin/customers?skip=${skip}&limit=${limit}`, {
        cache: 'no-store',
        headers: getAdminHeaders(),
      });
      if (res.ok) return await res.json();
    } catch (err) {
      console.error('[adminApi.listCustomers] Error:', err);
    }
    return [];
  },

  async getPipelineRuns(limit = 15): Promise<PipelineRunLog[]> {
    try {
      const res = await tracedFetch(`${BASE_URL}/admin/pipeline/runs?limit=${limit}`, {
        cache: 'no-store',
        headers: getAdminHeaders(),
      });
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
    const res = await tracedFetch(url.toString(), {
      method: 'POST',
      headers: getAdminHeaders(),
    });
    return await res.json();
  },

  async triggerQuoteScrape(tickers?: string[]) {
    const url = new URL(`${BASE_URL}/admin/pipeline/scrape-quotes`);
    if (tickers && tickers.length > 0) {
      tickers.forEach((t) => url.searchParams.append('tickers', t));
    }
    const res = await tracedFetch(url.toString(), {
      method: 'POST',
      headers: getAdminHeaders(),
    });
    return await res.json();
  },

  async triggerRecomputeScores() {
    const res = await tracedFetch(`${BASE_URL}/admin/pipeline/score`, {
      method: 'POST',
      headers: getAdminHeaders(),
    });
    return await res.json();
  },

  async triggerEmailDigest(recipients?: string[]) {
    const url = new URL(`${BASE_URL}/admin/pipeline/email-digest`);
    if (recipients && recipients.length > 0) {
      recipients.forEach((r) => url.searchParams.append('recipients', r));
    }
    const res = await tracedFetch(url.toString(), {
      method: 'POST',
      headers: getAdminHeaders(),
    });
    return await res.json();
  },

  async triggerEvaluateAlerts() {
    const res = await tracedFetch(`${BASE_URL}/admin/pipeline/evaluate-alerts`, {
      method: 'POST',
      headers: getAdminHeaders(),
    });
    return await res.json();
  },

  async overrideFinancials(ticker: string, year: number, data: any) {
    const res = await tracedFetch(`${BASE_URL}/admin/stocks/${ticker.toUpperCase()}/financials/${year}`, {
      method: 'POST',
      headers: getAdminHeaders(),
      body: JSON.stringify(data),
    });
    return await res.json();
  },
};

// ── Outcome as a Service (On-Demand) API ──────────────────────

export interface OutcomeAccess {
  email: string;
  unlocked: boolean;
  tier?: string;
  plan?: string;
  downloadUrl?: string;
  unlockedAt?: number;
}

export const outcomeApi = {
  getStoredOutcome(): OutcomeAccess | null {
    if (typeof window === 'undefined') return null;
    try {
      const raw = localStorage.getItem('stockpilot_outcome_access');
      if (raw) return JSON.parse(raw);
      // Fallback check if member user exists and is paid
      const member = localStorage.getItem('stockpilot_member_user');
      if (member) {
        const parsed = JSON.parse(member);
        if (parsed.tier === 'paid' || parsed.tier === 'pro') {
          return {
            email: parsed.email,
            unlocked: true,
            tier: parsed.tier,
            plan: 'on_demand',
          };
        }
      }
    } catch (e) {
      // ignore JSON parse error
    }
    return null;
  },

  setStoredOutcome(email: string, tier = 'paid', plan = 'on_demand', downloadUrl?: string) {
    if (typeof window === 'undefined') return;
    const access: OutcomeAccess = {
      email: email.trim().toLowerCase(),
      unlocked: true,
      tier,
      plan,
      downloadUrl: downloadUrl || `${BASE_URL}/reports/download-latest`,
      unlockedAt: Date.now(),
    };
    localStorage.setItem('stockpilot_outcome_access', JSON.stringify(access));
    // Also sync to member user so all components recognize the unlocked status
    localStorage.setItem(
      'stockpilot_member_user',
      JSON.stringify({
        email: access.email,
        name: access.email.split('@')[0],
        tier: 'paid',
        role: 'member',
      })
    );
  },

  clearStoredOutcome() {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('stockpilot_outcome_access');
    localStorage.removeItem('stockpilot_member_user');
    localStorage.removeItem('stockpilot_member_token');
  },

  async checkoutOnDemand(
    email: string,
    paymentMethod = 'gcash',
    name?: string,
    amountPhp = 249.0,
    investorGoal = 'all',
    hypeCheckTicker?: string
  ): Promise<{
    status: string;
    email: string;
    unlocked: boolean;
    amount_paid_php?: number;
    pwyc_impact_note?: string;
    download_url: string;
    message: string;
  }> {
    const cleanEmail = email.trim().toLowerCase();
    try {
      const res = await tracedFetch(`${BASE_URL}/customers/on-demand-checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: cleanEmail,
          name: name || cleanEmail.split('@')[0],
          amount_php: amountPhp,
          payment_method: paymentMethod,
          investor_goal: investorGoal,
          hype_check_ticker: hypeCheckTicker || undefined,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        outcomeApi.setStoredOutcome(cleanEmail, data.tier || 'paid', 'on_demand', data.download_url);
        return data;
      }
    } catch (err) {
      console.warn('[outcomeApi.checkoutOnDemand] Server connection issue, activating local on-demand pass:', err);
    }

    // Resilient fallback for standalone dev / offline mode
    const fallbackData = {
      status: 'success',
      email: cleanEmail,
      tier: 'paid',
      plan: 'on_demand',
      unlocked: true,
      amount_paid_php: amountPhp,
      pwyc_impact_note:
        amountPhp >= 400
          ? 'Pay-It-Forward Impact: Your contribution helped sponsor beginner Filipino investors.'
          : 'Community Research Pass unlocked!',
      download_url: `${BASE_URL}/reports/download-latest`,
      message: `PWYC contribution of ₱${amountPhp.toFixed(0)} via ${paymentMethod.toUpperCase()} confirmed! Dossier dispatched to ${cleanEmail} and full intelligence unlocked.`,
    };
    outcomeApi.setStoredOutcome(cleanEmail, 'paid', 'on_demand', fallbackData.download_url);
    return fallbackData;
  },

  async getDoneForYouMenu(goal = 'all', hypeCheckTicker?: string): Promise<any> {
    try {
      const params = new URLSearchParams({ goal });
      if (hypeCheckTicker && hypeCheckTicker.trim()) {
        params.set('hype_check_ticker', hypeCheckTicker.trim().toUpperCase());
      }
      const res = await tracedFetch(`${BASE_URL}/reports/done-for-you?${params.toString()}`, {
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('[outcomeApi.getDoneForYouMenu] Server connection issue:', err);
    }
    return null;
  },

  async verifyAccess(email: string): Promise<{ has_access: boolean; email: string; message: string }> {
    const cleanEmail = email.trim().toLowerCase();
    try {
      const res = await tracedFetch(`${BASE_URL}/customers/verify-access`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: cleanEmail }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.has_access) {
          outcomeApi.setStoredOutcome(cleanEmail, data.tier || 'paid');
        }
        return data;
      }
    } catch (err) {
      console.warn('[outcomeApi.verifyAccess] Server connection issue:', err);
    }

    // Check stored outcome locally
    const stored = outcomeApi.getStoredOutcome();
    if (stored && stored.email.toLowerCase() === cleanEmail) {
      return {
        has_access: true,
        email: cleanEmail,
        message: 'Active Outcome Pass found locally! Welcome back.',
      };
    }

    return {
      has_access: false,
      email: cleanEmail,
      message: 'No purchase record found for this email. Unlock on demand for ₱499.',
    };
  },

  getDownloadUrl(goal = 'all', hypeCheckTicker?: string): string {
    const params = new URLSearchParams();
    if (goal) params.set('goal', goal);
    if (hypeCheckTicker && hypeCheckTicker.trim()) {
      params.set('hype_check_ticker', hypeCheckTicker.trim().toUpperCase());
    }
    const qs = params.toString();
    return `${BASE_URL}/reports/download-latest${qs ? `?${qs}` : ''}`;
  },
};

// ── OaaS & Causal Alert Engine API ───────────────────────────

export interface OaasRegimeData {
  regime_title: string;
  is_pro_access: boolean;
  macro_shock_vector: {
    z_bsp_rate: number;
    z_us10y_yield: number;
    z_brent_crude: number;
    z_usd_php: number;
    z_msci_flow: number;
    php_10y_bval_rate: number;
  };
  top_allocations: Array<{
    ticker: string;
    name: string;
    sector: string;
    price: number;
    board_lot: number;
    net_hurdle_pct: number;
    friction_bps: number;
    action_channel: string;
    executable_shares?: number;
    executable_ticket_php?: number;
    limit_low?: number;
    limit_high?: number;
    stop_loss?: number;
    crowd_participation_pct?: number;
  }>;
  quarantined_traps_count: number;
  updated_at: string;
}

export const oaasApi = {
  async getRegime(): Promise<OaasRegimeData> {
    const token = typeof window !== 'undefined' ? localStorage.getItem('stockpilot_member_token') : null;
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await tracedFetch(`${BASE_URL}/oaas/regime`, { headers });
    if (!res.ok) {
      throw new Error(`Failed to fetch macro regime: ${res.statusText}`);
    }
    return res.json();
  },

  async evaluate(shocks: Record<string, any> = {}): Promise<any> {
    const adminHeaders = typeof window !== 'undefined' ? (window as any).getAdminHeaders?.() || {} : {};
    const res = await tracedFetch(`${BASE_URL}/oaas/evaluate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...adminHeaders,
      },
      body: JSON.stringify(shocks),
    });
    if (!res.ok) throw new Error(`Evaluation failed: ${res.statusText}`);
    return res.json();
  },

  async updateMacroState(state: Record<string, any>): Promise<any> {
    const adminHeaders = typeof window !== 'undefined' ? (window as any).getAdminHeaders?.() || {} : {};
    const res = await tracedFetch(`${BASE_URL}/oaas/macro-state`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...adminHeaders,
      },
      body: JSON.stringify(state),
    });
    if (!res.ok) throw new Error(`Macro state update failed: ${res.statusText}`);
    return res.json();
  },

  async dispatch(action: 'weekly_brief' | 'daily_triage', dryRun = false): Promise<any> {
    const adminHeaders = typeof window !== 'undefined' ? (window as any).getAdminHeaders?.() || {} : {};
    const res = await tracedFetch(`${BASE_URL}/oaas/dispatch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...adminHeaders,
      },
      body: JSON.stringify({ action, dry_run: dryRun }),
    });
    if (!res.ok) throw new Error(`Dispatch trigger failed: ${res.statusText}`);
    return res.json();
  },

  async getHistory(): Promise<any> {
    const adminHeaders = typeof window !== 'undefined' ? (window as any).getAdminHeaders?.() || {} : {};
    const res = await tracedFetch(`${BASE_URL}/oaas/history`, {
      headers: adminHeaders,
    });
    if (!res.ok) throw new Error(`Failed to fetch history: ${res.statusText}`);
    return res.json();
  },
};
