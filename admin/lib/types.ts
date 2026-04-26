export interface Industry {
  id: string;
  name: string;
  slug: string;
}

export interface Skill {
  id: string;
  name: string;
  slug: string;
}

export interface PipelineStartup {
  id: string;
  name: string;
  slug: string;
  description: string;
  stage: string;
  status: string;
  created_at: string;
  industries: Industry[];
  assignment_count: number;
  dimensions_configured: boolean;
}

export interface StartupDetail {
  id: string;
  name: string;
  slug: string;
  description: string;
  website_url: string | null;
  logo_url: string | null;
  stage: string;
  status: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
}

export interface AdminStartup {
  id: string;
  name: string;
  slug: string;
  description: string;
  website_url: string | null;
  logo_url: string | null;
  stage: string;
  status: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
  industries: Industry[];
  created_at: string;
}

export interface CreateStartupInput {
  name: string;
  description: string;
  website_url?: string;
  stage: string;
  status: string;
  location_city?: string;
  location_state?: string;
  location_country: string;
  industry_ids: string[];
}

export interface ExpertApplication {
  id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  bio: string;
  years_experience: number;
  application_status: string;
  created_at: string;
}

export interface ApprovedExpert {
  id: string;
  user_id: string;
  bio: string;
  years_experience: number;
  application_status: string;
  industries: Industry[];
  skills: Skill[];
  created_at: string;
}

export interface Assignment {
  id: string;
  startup_id: string;
  expert_id: string;
  assigned_by: string;
  status: string;
  assigned_at: string;
  responded_at: string | null;
}

export interface Dimension {
  id: string;
  dimension_name: string;
  dimension_slug: string;
  weight: number;
  sort_order: number;
}

export interface DDTemplate {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  industry_slug: string | null;
  stage: string | null;
  created_at: string;
  dimensions: Dimension[];
}

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: string;
}

export interface Founder {
  id: string;
  name: string;
  title: string | null;
  linkedin_url: string | null;
}

export interface FundingRound {
  id: string;
  round_name: string;
  amount: string | null;
  date: string | null;
  lead_investor: string | null;
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

export interface EnrichmentStatusResponse {
  enrichment_status: "none" | "running" | "complete" | "failed";
  enrichment_error: string | null;
  enriched_at: string | null;
}

export interface StartupFullDetail {
  id: string;
  name: string;
  slug: string;
  description: string;
  tagline: string | null;
  website_url: string | null;
  logo_url: string | null;
  stage: string;
  status: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
  founded_date: string | null;
  total_funding: string | null;
  employee_count: string | null;
  linkedin_url: string | null;
  twitter_url: string | null;
  crunchbase_url: string | null;
  competitors: string | null;
  tech_stack: string | null;
  key_metrics: string | null;
  hiring_signals: string | null;
  patents: string | null;
  enrichment_status: "none" | "running" | "complete" | "failed";
  enrichment_error: string | null;
  enriched_at: string | null;
  ai_score: number | null;
  industries: { id: string; name: string; slug: string }[];
  founders: Founder[];
  funding_rounds: FundingRound[];
  ai_review: AIReview | null;
  form_sources: string[];
  data_sources: Record<string, string>;
}

// Scout types
export interface StartupCandidate {
  name: string;
  website_url: string | null;
  description: string;
  stage: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
  founders: string | null;
  funding_raised: string | null;
  key_investors: string | null;
  linkedin_url: string | null;
  founded_year: string | null;
  already_on_platform?: boolean;
  existing_status?: string;
  existing_id?: string;
}

export interface ScoutChatResponse {
  reply: string;
  startups: StartupCandidate[];
  citations: string[];
}

export interface ScoutAddResponse {
  created: { id: string; name: string; slug: string; status: string }[];
  skipped: string[];
  message: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  startups?: StartupCandidate[];
}

// Triage feed item — union of different item types
export type TriageItemType = "startup" | "expert_application" | "assignment";

export interface TriageItem {
  type: TriageItemType;
  id: string;
  timestamp: string;
  data: PipelineStartup | ExpertApplication | Assignment;
}

export interface InvestorItem {
  id: string;
  firm_name: string;
  partner_name: string;
  email: string | null;
  website: string | null;
  stage_focus: string | null;
  sector_focus: string | null;
  location: string | null;
  aum_fund_size: string | null;
  recent_investments: string[] | null;
  fit_reason: string | null;
  source_startups: { id: string; name: string }[];
  created_at: string;
}

export interface InvestorListResponse {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: InvestorItem[];
}

export interface InvestorBatchStatus {
  id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  total_startups: number;
  processed_startups: number;
  current_startup_name: string | null;
  investors_found: number;
  error: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
}

// ── Feedback ──────────────────────────────────────────────────────────

export interface FeedbackRecommendation {
  title: string;
  description: string;
  priority: number;
}

export interface FeedbackTranscriptMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface FeedbackItem {
  id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  status: string;
  category: string | null;
  severity: string | null;
  area: string | null;
  summary: string | null;
  recommendations: FeedbackRecommendation[] | null;
  transcript: FeedbackTranscriptMessage[] | null;
  page_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackListResponse {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: FeedbackItem[];
}

// ── Investor Rankings ────────────────────────────────────────────────

export interface RankedInvestorItem {
  id: string;
  investor_id: string;
  firm_name: string;
  partner_name: string;
  location: string | null;
  stage_focus: string | null;
  sector_focus: string | null;
  overall_score: number;
  portfolio_performance: number;
  deal_activity: number;
  exit_track_record: number;
  stage_expertise: number;
  sector_expertise: number;
  follow_on_rate: number;
  network_quality: number;
  narrative: string;
  scored_at: string;
}

export interface RankedInvestorListResponse {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: RankedInvestorItem[];
}

export interface RankingBatchStatus {
  id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  total_investors: number;
  processed_investors: number;
  current_investor_name: string | null;
  investors_scored: number;
  error: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
}

// ── Marketing ─────────────────────────────────────────────────────────

export interface MarketingJob {
  id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  subject: string;
  total_recipients: number;
  sent_count: number;
  failed_count: number;
  current_investor_name: string | null;
  from_address: string;
  error: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}

export interface SentEmail {
  id: string;
  investor_id: string;
  firm_name: string;
  partner_name: string;
  email: string;
  status: "sent" | "failed";
  error: string | null;
  sent_at: string | null;
}

// ── Email Verification ──────────────────────────────────────────────

export interface VerificationJob {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  total_recipients: number;
  verified_count: number;
  corrected_count: number;
  bounced_count: number;
  skipped_count: number;
  current_investor_name: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}
