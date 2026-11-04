export type QualityCategory = 'Highest Quality' | 'Strong Growth' | 'Watchlist' | 'Weak';

export type SectorGroup =
  | 'Bank'
  | 'REIT'
  | 'Conglomerate'
  | 'Property'
  | 'Industrial'
  | 'Mining & Oil'
  | 'Services'
  | 'General';

export interface LayerScore {
  score: number;
  weight: number;
  factors: Record<string, number | null>;
}

export interface ValuationModelResult {
  value: number | null;
  status: string;
}

export interface StockRanking {
  rank: number;
  ticker: string;
  name: string;
  sector: string;
  scoringGroup: SectorGroup;
  score: number;
  confidence: number;
  category: QualityCategory;
  currentPrice: number;
  intrinsicValue: number | null;
  mosPct: number | null;
  dividendYield: number | null;
  pe: number | null;
  pb: number | null;
  roe: number | null;
  deRatio: number | null;
}

export interface StockDetail extends StockRanking {
  marketCap: number;
  dpsLast: number | null;
  dividendCagr5y: number | null;
  fcfPerShare: number | null;
  revenueCagr: number | null;
  requiredReturn: number;
  layers: {
    health: LayerScore;
    improvement: LayerScore;
    persistence: LayerScore;
  };
  valuation: {
    ddm: ValuationModelResult;
    epsPe: ValuationModelResult;
    dcf: ValuationModelResult;
    conglomerateDiscountApplied: boolean;
  };
  historicalFinancials: {
    year: number;
    revenue: number;
    netIncome: number;
    equity: number;
    eps: number;
    dps: number | null;
  }[];
}
