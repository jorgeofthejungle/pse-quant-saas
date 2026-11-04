/**
 * frontend/src/lib/db.ts — Database Client for TypeScript Web Portal
 * Connects to PostgreSQL (via pg) or SQLite (via native Node node:sqlite) with
 * transparent fallback to mock data when database is empty or offline.
 */

import path from 'path';
import fs from 'fs';
import { StockRanking, StockDetail, SectorGroup, QualityCategory } from '@/types/stock';
import { MOCK_RANKINGS, MOCK_STOCK_DETAILS } from './mockData';

// Sector mapping helper
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

/**
 * Locates the local SQLite database file if present in the repository.
 */
function getSqlitePath(): string | null {
  const candidatePaths = [
    path.resolve(process.cwd(), '../backend/pse_quant/db/pse_local.db'),
    path.resolve(process.cwd(), 'backend/pse_quant/db/pse_local.db'),
    path.resolve(process.cwd(), 'pse_local.db'),
  ];
  for (const p of candidatePaths) {
    if (fs.existsSync(/*turbopackIgnore: true*/ p)) {
      return p;
    }
  }
  return null;
}

/**
 * Executes a read query against PostgreSQL or SQLite.
 */
async function queryDatabase<T = any>(sql: string, params: any[] = []): Promise<T[]> {
  const dbUrl = process.env.DATABASE_URL;

  // 1. PostgreSQL connection
  if (dbUrl && (dbUrl.startsWith('postgres://') || dbUrl.startsWith('postgresql://'))) {
    try {
      const { Pool } = await import('pg');
      const pool = new Pool({
        connectionString: dbUrl.replace('postgres://', 'postgresql://'),
        ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
      });
      const res = await pool.query(sql, params);
      await pool.end();
      return res.rows as T[];
    } catch (err) {
      console.warn('[db.ts] PostgreSQL query failed, attempting SQLite fallback:', err);
    }
  }

  // 2. Native SQLite connection (Node 22+)
  const sqliteFile = getSqlitePath();
  if (sqliteFile) {
    try {
      // @ts-expect-error Node 22+ built-in sqlite module
      const { DatabaseSync } = await import('node:sqlite');
      const db = new DatabaseSync(sqliteFile, { readOnly: true });

      // Convert $1, $2 placeholders to ? for SQLite
      let sqliteSql = sql;
      for (let i = 1; i <= params.length; i++) {
        sqliteSql = sqliteSql.replace(new RegExp(`\\$${i}`, 'g'), '?');
      }

      const stmt = db.prepare(sqliteSql);
      const rows = stmt.all(...params) as T[];
      db.close();
      return rows;
    } catch (err) {
      console.warn('[db.ts] SQLite query error:', err);
    }
  }

  return [];
}

/**
 * Transforms a raw score row and breakdown_json into StockRanking interface.
 */
function formatRanking(row: any): StockRanking {
  const bj = typeof row.breakdown_json === 'string' ? JSON.parse(row.breakdown_json) : (row.breakdown_json || {});
  
  return {
    rank: row.rank || bj.rank || 0,
    ticker: row.ticker || bj.ticker,
    name: bj.name || row.name || row.ticker,
    sector: bj.sector || row.sector || 'General',
    scoringGroup: mapScoringGroup(bj.scoring_group, bj.sector || ''),
    score: Number((row.score || bj.score || 0).toFixed(1)),
    confidence: bj.confidence || row.confidence || 1.0,
    category: (row.category || bj.category || 'Watchlist') as QualityCategory,
    currentPrice: bj.current_price || 0,
    intrinsicValue: bj.intrinsic_value !== undefined ? bj.intrinsic_value : null,
    mosPct: bj.mos_pct !== undefined ? bj.mos_pct : null,
    dividendYield: bj.dividend_yield !== undefined ? bj.dividend_yield : null,
    pe: bj.pe !== undefined ? bj.pe : null,
    pb: bj.pb !== undefined ? bj.pb : null,
    roe: bj.roe !== undefined ? bj.roe : null,
    deRatio: bj.de_ratio !== undefined ? bj.de_ratio : null,
  };
}

/**
 * Fetches ranked stocks for a specific portfolio from DB with fallback to mock data.
 */
export async function getRankings(portfolioType = 'unified'): Promise<StockRanking[]> {
  try {
    const rows = await queryDatabase(
      `SELECT s.ticker, s.score, s.rank, s.category, s.confidence, s.breakdown_json, st.name, st.sector
       FROM scores s
       LEFT JOIN stocks st ON s.ticker = st.ticker
       WHERE s.portfolio_type = $1
       ORDER BY s.rank ASC, s.score DESC`,
      [portfolioType]
    );

    if (rows && rows.length > 0) {
      return rows.map(formatRanking);
    }
  } catch (e) {
    console.warn('[db.ts] Error fetching rankings from DB, using fallback mock:', e);
  }

  return MOCK_RANKINGS;
}

/**
 * Fetches comprehensive stock details for a single ticker.
 */
export async function getStockDetail(ticker: string): Promise<StockDetail | null> {
  const cleanTicker = ticker.toUpperCase().trim();

  try {
    const rows = await queryDatabase(
      `SELECT s.ticker, s.score, s.rank, s.category, s.confidence, s.breakdown_json, st.name, st.sector, st.is_reit, st.is_bank
       FROM scores s
       LEFT JOIN stocks st ON s.ticker = st.ticker
       WHERE s.ticker = $1 AND s.portfolio_type = 'unified'
       ORDER BY s.run_date DESC LIMIT 1`,
      [cleanTicker]
    );

    if (rows && rows.length > 0) {
      const row = rows[0];
      const ranking = formatRanking(row);
      const bj = typeof row.breakdown_json === 'string' ? JSON.parse(row.breakdown_json) : (row.breakdown_json || {});
      const breakdown = bj.breakdown || {};
      const layers = breakdown.layers || {};
      const val = bj.valuation || {};

      // Also pull historical financial statements
      const finRows = await queryDatabase(
        `SELECT year, revenue, net_income, equity, eps, dps
         FROM financials
         WHERE ticker = $1
         ORDER BY year DESC LIMIT 5`,
        [cleanTicker]
      );

      const financials = (finRows && finRows.length > 0)
        ? finRows.map((f: any) => ({
            year: f.year,
            revenue: f.revenue || 0,
            netIncome: f.net_income || 0,
            equity: f.equity || 0,
            eps: f.eps || 0,
            dps: f.dps !== undefined ? f.dps : null,
          }))
        : (MOCK_STOCK_DETAILS[cleanTicker]?.historicalFinancials || []);

      return {
        ...ranking,
        marketCap: bj.market_cap || 0,
        dpsLast: bj.dps_last ?? null,
        dividendCagr5y: bj.dividend_cagr_5y ?? null,
        fcfPerShare: bj.fcf_per_share ?? null,
        revenueCagr: bj.revenue_cagr ?? null,
        requiredReturn: bj.required_return || 0.125,
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
            status: val.ddm?.status || 'DDM not applicable',
          },
          epsPe: {
            value: val.eps_pe?.value ?? null,
            status: val.eps_pe?.status || 'EPS-PE calculated',
          },
          dcf: {
            value: val.dcf?.value ?? null,
            status: val.dcf?.status || 'DCF calculated',
          },
          conglomerateDiscountApplied: Boolean(val.conglomerate_discount_applied),
        },
        historicalFinancials: financials,
      };
    }
  } catch (e) {
    console.warn(`[db.ts] Error fetching stock detail for ${cleanTicker}:`, e);
  }

  // Fallback to static mock details if present
  return MOCK_STOCK_DETAILS[cleanTicker] || null;
}

/**
 * Gets watchlist items by ticker list.
 */
export async function getWatchlistStocks(tickers: string[]): Promise<StockRanking[]> {
  const all = await getRankings();
  const set = new Set(tickers.map((t) => t.toUpperCase()));
  return all.filter((s) => set.has(s.ticker.toUpperCase()));
}
