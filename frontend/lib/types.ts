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

export interface StartupDetail extends StartupCard {
  founded_date: string | null;
  media: MediaItem[];
  score_history: ScoreHistory[];
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

export interface ExpertApplication {
  id: string;
  bio: string;
  years_experience: number;
  application_status: string;
  industries: string[];
  skills: string[];
  created_at: string;
}
