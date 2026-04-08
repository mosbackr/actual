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
  stage: string;
  status: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
}

export interface ExpertApplication {
  id: string;
  user_id: string;
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
  created_at: string;
  dimensions: Dimension[];
}

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: string;
}

// Triage feed item — union of different item types
export type TriageItemType = "startup" | "expert_application" | "assignment";

export interface TriageItem {
  type: TriageItemType;
  id: string;
  timestamp: string;
  data: PipelineStartup | ExpertApplication | Assignment;
}
