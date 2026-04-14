export interface InsightsSummary {
  total_startups: number;
  filtered_startups: number;
  avg_ai_score: number | null;
  total_funding: string;
  total_funding_raw: number;
  industry_count: number;
  top_verdict: { verdict: string | null; count: number };
  avg_stage: string | null;
  median_stage: string | null;
  new_this_month: number;
}

export interface ScatterPoint {
  id: string;
  slug: string;
  name: string;
  ai_score: number;
  expert_score: number;
  industry: string;
  stage: string;
  total_funding_raw: number;
}

export interface HistogramBucket {
  bucket: string;
  count: number;
}

export interface VerdictCount {
  verdict: string;
  count: number;
}

export interface ScoresData {
  scatter: ScatterPoint[];
  histogram: HistogramBucket[];
  verdicts: VerdictCount[];
}

export interface StageFunding {
  stage: string;
  label: string;
  total_amount: number;
  count: number;
}

export interface RecentRound {
  startup_name: string;
  startup_slug: string;
  amount: string;
  stage: string;
  date: string | null;
  round_name: string;
}

export interface FundingData {
  by_stage: StageFunding[];
  recent_rounds: RecentRound[];
}

export interface IndustryRow {
  name: string;
  slug: string;
  avg_ai_score: number | null;
  count: number;
  total_funding: number;
}

export interface MonthlyCount {
  month: string;
  count: number;
}

export interface RecentDealFlowRound {
  name: string;
  slug: string;
  round_name: string;
  amount: string | null;
  date: string | null;
  industry: string;
  ai_score: number | null;
}

export interface DealFlowData {
  monthly: MonthlyCount[];
  recent: RecentDealFlowRound[];
}

export interface FilterOptions {
  available_countries: string[];
  available_states: string[];
  available_industries: { name: string; slug: string }[];
}

export interface InsightsResponse {
  summary: InsightsSummary;
  scores: ScoresData;
  funding: FundingData;
  industries: IndustryRow[];
  deal_flow: DealFlowData;
  filters: FilterOptions;
}
