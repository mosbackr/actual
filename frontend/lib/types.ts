export interface Industry {
  id: string;
  name: string;
  slug: string;
}

export interface StartupCard {
  id: string;
  name: string;
  slug: string;
  description: string;
  tagline: string | null;
  website_url: string | null;
  logo_url: string | null;
  stage: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
  ai_score: number | null;
  expert_score: number | null;
  user_score: number | null;
  industries: Industry[];
  form_sources: string[];
}

export interface MediaItem {
  id: string;
  url: string;
  title: string;
  source: string;
  media_type: string;
  published_at: string | null;
}

export interface ScoreHistory {
  score_type: string;
  score_value: number;
  dimensions_json: Record<string, number> | null;
  recorded_at: string;
}

export interface StartupDimension {
  name: string;
  slug: string;
  weight: number;
}

export interface StartupDetail extends StartupCard {
  founded_date: string | null;
  total_funding: string | null;
  employee_count: string | null;
  linkedin_url: string | null;
  twitter_url: string | null;
  crunchbase_url: string | null;
  competitors: string | null;
  tech_stack: string | null;
  key_metrics: string | null;
  company_status: string | null;
  revenue_estimate: string | null;
  business_model: string | null;
  founders: Founder[];
  funding_rounds: FundingRound[];
  ai_review: AIReview | null;
  media: MediaItem[];
  score_history: ScoreHistory[];
  dimensions: StartupDimension[];
  data_sources: Record<string, string>;
}

export interface PaginatedStartups {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: StartupCard[];
}

export interface Stage {
  value: string;
  label: string;
}

export interface Founder {
  name: string;
  title: string | null;
  linkedin_url: string | null;
  is_founder: boolean;
  prior_experience: string | null;
  education: string | null;
}

export interface FundingRound {
  round_name: string;
  amount: string | null;
  date: string | null;
  lead_investor: string | null;
  other_investors: string | null;
  pre_money_valuation: string | null;
  post_money_valuation: string | null;
}

export interface DimensionScore {
  dimension_name: string;
  score: number;
  reasoning: string;
}

export interface AIReview {
  overall_score: number;
  investment_thesis: string;
  key_risks: string;
  verdict: string;
  dimension_scores: DimensionScore[];
  created_at: string;
}

export interface Review {
  id: string;
  startup_id: string;
  user_id: string;
  user_name: string | null;
  review_type: "contributor" | "community";
  overall_score: number;
  dimension_scores: Record<string, number> | null;
  comment: string | null;
  upvotes: number;
  downvotes: number;
  current_user_vote: "up" | "down" | null;
  created_at: string;
}


export interface ExpertApplication {
  id: string;
  bio: string;
  years_experience: number;
  application_status: string;
  industries: string[];
  skills: string[];
  created_at: string;
}

export interface AnalysisListItem {
  id: string;
  company_name: string;
  status: string;
  overall_score: number | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface AnalysisDocument {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
}

export interface AnalysisReportSummary {
  id: string;
  agent_type: string;
  status: string;
  score: number | null;
  summary: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AnalysisReportFull {
  id: string;
  agent_type: string;
  status: string;
  score: number | null;
  summary: string | null;
  report: string | null;
  key_findings: string[] | null;
  error: string | null;
}

export interface AnalysisDetail {
  id: string;
  company_name: string;
  status: string;
  current_agent: string | null;
  overall_score: number | null;
  fundraising_likelihood: number | null;
  recommended_raise: string | null;
  exit_likelihood: number | null;
  expected_exit_value: string | null;
  expected_exit_timeline: string | null;
  executive_summary: string | null;
  publish_consent: boolean;
  is_free_analysis: boolean;
  startup_id: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
  reports: AnalysisReportSummary[];
  documents: AnalysisDocument[];
}

// ── Analyst types ────────────────────────────────────────────────────

export interface AnalystConversationSummary {
  id: string;
  title: string;
  message_count: number;
  is_free_conversation: boolean;
  updated_at: string | null;
}

export interface AnalystMessageData {
  id: string;
  role: "user" | "assistant";
  content: string;
  charts: AnalystChartConfig[] | null;
  citations: AnalystCitation[] | null;
  created_at: string | null;
}

export interface AnalystChartConfig {
  type: "bar" | "line" | "pie" | "scatter" | "area";
  title: string;
  data: Record<string, unknown>[];
  xKey?: string;
  yKeys?: string[];
  nameKey?: string;
  dataKey?: string;
  colors?: string[];
}

export interface AnalystCitation {
  url: string;
  title: string;
}

export interface AnalystReportSummary {
  id: string;
  title: string;
  format: "docx" | "xlsx";
  status: "pending" | "generating" | "complete" | "failed";
  file_size_bytes: number | null;
  created_at: string | null;
}

export interface AnalystConversationDetail {
  id: string;
  title: string;
  is_free_conversation: boolean;
  message_count: number;
  share_token: string | null;
  created_at: string | null;
  updated_at: string | null;
  messages: AnalystMessageData[];
  reports?: AnalystReportSummary[];
}

export interface AnalystSharedConversation {
  title: string;
  message_count: number;
  messages: AnalystMessageData[];
}

// ── Billing types ─────────────────────────────────────────────────────

export interface BillingStatus {
  subscription_status: "none" | "active" | "cancelled" | "past_due";
  subscription_tier: "starter" | "professional" | "unlimited" | null;
  subscription_period_end: string | null;
  has_stripe_customer: boolean;
}

// ── Notification types ────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  type: "analysis_complete" | "report_ready";
  title: string;
  message: string;
  link: string;
  read: boolean;
  created_at: string | null;
}

export interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
}

export interface ReportListItem {
  id: string;
  conversation_id: string;
  title: string;
  conversation_title: string;
  format: "docx" | "xlsx" | "pdf" | "pptx";
  status: "pending" | "generating" | "complete" | "failed";
  file_size_bytes: number | null;
  created_at: string | null;
}

export interface InvestmentMemo {
  id: string;
  status: "pending" | "researching" | "generating" | "formatting" | "complete" | "failed";
  content: string | null;
  pdf_url: string | null;
  docx_url: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}
