import type {
  AdminStartup,
  AdminUser,
  AIReview,
  ApprovedExpert,
  Assignment,
  CreateStartupInput,
  DDTemplate,
  Dimension,
  EnrichmentStatusResponse,
  ExpertApplication,
  FeedbackItem,
  FeedbackListResponse,
  InvestorBatchStatus,
  InvestorListResponse,
  PipelineStartup,
  RankedInvestorListResponse,
  RankingBatchStatus,
  ScoutAddResponse,
  ScoutChatResponse,
  StartupCandidate,
  StartupDetail,
  StartupFullDetail,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

async function apiFetch<T>(path: string, token: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const adminApi = {
  // Startups
  getPipeline: (token: string) =>
    apiFetch<PipelineStartup[]>("/api/admin/startups/pipeline", token),

  getAllStartups: (token: string, status?: string) =>
    apiFetch<AdminStartup[]>(`/api/admin/startups${status ? `?status=${status}` : ""}`, token),

  createStartup: (token: string, body: CreateStartupInput) =>
    apiFetch<StartupDetail>("/api/admin/startups", token, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateStartup: (token: string, id: string, body: Record<string, unknown>) =>
    apiFetch<StartupDetail>(`/api/admin/startups/${id}`, token, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  fetchLogo: (token: string, startupId: string) =>
    apiFetch<{ logo_url: string; domain: string }>(`/api/admin/startups/${startupId}/fetch-logo`, token, {
      method: "POST",
    }),

  getIndustries: (token: string) =>
    apiFetch<{ id: string; name: string; slug: string }[]>("/api/industries", token),

  // Expert applications
  getApplications: (token: string) =>
    apiFetch<ExpertApplication[]>("/api/admin/experts/applications", token),

  approveExpert: (token: string, profileId: string) =>
    apiFetch<ExpertApplication>(`/api/admin/experts/${profileId}/approve`, token, {
      method: "PUT",
    }),

  rejectExpert: (token: string, profileId: string) =>
    apiFetch<ExpertApplication>(`/api/admin/experts/${profileId}/reject`, token, {
      method: "PUT",
    }),

  // Approved experts
  getApprovedExperts: (token: string) =>
    apiFetch<ApprovedExpert[]>("/api/admin/experts", token),

  // Assignments
  getAssignments: (token: string, startupId: string) =>
    apiFetch<Assignment[]>(`/api/admin/startups/${startupId}/assignments`, token),

  assignExpert: (token: string, startupId: string, expertId: string) =>
    apiFetch<Assignment>(`/api/admin/startups/${startupId}/assign-expert`, token, {
      method: "POST",
      body: JSON.stringify({ expert_id: expertId }),
    }),

  deleteAssignment: (token: string, assignmentId: string) =>
    apiFetch<void>(`/api/admin/assignments/${assignmentId}`, token, {
      method: "DELETE",
    }),

  // Templates
  getTemplates: (token: string) =>
    apiFetch<DDTemplate[]>("/api/admin/dd-templates", token),

  getTemplate: (token: string, id: string) =>
    apiFetch<DDTemplate>(`/api/admin/dd-templates/${id}`, token),

  createTemplate: (token: string, body: { name: string; description?: string; industry_slug?: string; stage?: string; dimensions: { dimension_name: string; weight: number; sort_order: number }[] }) =>
    apiFetch<DDTemplate>("/api/admin/dd-templates", token, {
      method: "POST",
      body: JSON.stringify({
        ...body,
        industry_slug: body.industry_slug || null,
        stage: body.stage || null,
      }),
    }),

  updateTemplate: (token: string, id: string, body: { name: string; description?: string; industry_slug?: string; stage?: string; dimensions: { dimension_name: string; weight: number; sort_order: number }[] }) =>
    apiFetch<DDTemplate>(`/api/admin/dd-templates/${id}`, token, {
      method: "PUT",
      body: JSON.stringify({
        ...body,
        industry_slug: body.industry_slug || null,
        stage: body.stage || null,
      }),
    }),

  deleteTemplate: (token: string, id: string) =>
    apiFetch<void>(`/api/admin/dd-templates/${id}`, token, {
      method: "DELETE",
    }),

  // Dimensions
  getDimensions: (token: string, startupId: string) =>
    apiFetch<Dimension[]>(`/api/admin/startups/${startupId}/dimensions`, token),

  applyTemplate: (token: string, startupId: string, templateId: string) =>
    apiFetch<{ template_id: string; dimensions: Dimension[] }>(
      `/api/admin/startups/${startupId}/apply-template`, token, {
        method: "POST",
        body: JSON.stringify({ template_id: templateId }),
      },
    ),

  updateDimensions: (token: string, startupId: string, dimensions: { dimension_name: string; weight: number; sort_order: number }[]) =>
    apiFetch<Dimension[]>(`/api/admin/startups/${startupId}/dimensions`, token, {
      method: "PUT",
      body: JSON.stringify({ dimensions }),
    }),

  // Users
  getUsers: (token: string, role?: string) =>
    apiFetch<AdminUser[]>(`/api/admin/users${role ? `?role=${role}` : ""}`, token),

  // Scout
  scoutChat: (token: string, message: string, history: { role: string; content: string }[]) =>
    apiFetch<ScoutChatResponse>("/api/admin/scout/chat", token, {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),

  scoutAdd: (token: string, startups: StartupCandidate[]) =>
    apiFetch<ScoutAddResponse>("/api/admin/scout/add", token, {
      method: "POST",
      body: JSON.stringify({ startups }),
    }),

  // Enrichment
  triggerEnrichment: (token: string, startupId: string) =>
    apiFetch<{ status: string }>(`/api/admin/startups/${startupId}/enrich`, token, {
      method: "POST",
    }),

  getEnrichmentStatus: (token: string, startupId: string) =>
    apiFetch<EnrichmentStatusResponse>(`/api/admin/startups/${startupId}/enrichment-status`, token),

  getAIReview: (token: string, startupId: string) =>
    apiFetch<AIReview>(`/api/admin/startups/${startupId}/ai-review`, token),

  getStartupFullDetail: (token: string, startupId: string) =>
    apiFetch<StartupFullDetail>(`/api/admin/startups/${startupId}/full-detail`, token),

  // Batch pipeline
  async startBatch(token: string, jobType: string, refreshDays?: number) {
    return apiFetch<{ job_id: string; status: string; total_steps: number }>(
      "/api/admin/batch/start",
      token,
      { method: "POST", body: JSON.stringify({ job_type: jobType, refresh_days: refreshDays || 30 }) }
    );
  },
  async pauseBatch(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/batch/${jobId}/pause`, token, { method: "POST" });
  },
  async resumeBatch(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/batch/${jobId}/resume`, token, { method: "POST" });
  },
  async cancelBatch(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/batch/${jobId}/cancel`, token, { method: "POST" });
  },
  async getActiveBatch(token: string) {
    return apiFetch<any>("/api/admin/batch/active", token);
  },
  async getBatchSteps(token: string, jobId: string, params?: string) {
    const qs = params ? `?${params}` : "";
    return apiFetch<any>(`/api/admin/batch/${jobId}/steps${qs}`, token);
  },
  async getBatchInvestors(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/batch/${jobId}/investors`, token);
  },
  async getBatchStartups(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/batch/${jobId}/startups`, token);
  },
  async getBatchLog(token: string, jobId: string, page?: number) {
    const qs = page ? `?page=${page}` : "";
    return apiFetch<any>(`/api/admin/batch/${jobId}/log${qs}`, token);
  },

  // EDGAR pipeline
  async startEdgar(token: string, scanMode: string, discoverDays?: number, formTypes?: string[]) {
    const body: Record<string, any> = { scan_mode: scanMode };
    if (discoverDays !== undefined) {
      body.discover_days = discoverDays;
    }
    if (formTypes !== undefined && formTypes.length > 0) {
      body.form_types = formTypes;
    }
    return apiFetch<{ job_id: string; status: string; total_steps: number }>(
      "/api/admin/edgar/start",
      token,
      { method: "POST", body: JSON.stringify(body) }
    );
  },
  async pauseEdgar(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/edgar/${jobId}/pause`, token, { method: "POST" });
  },
  async resumeEdgar(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/edgar/${jobId}/resume`, token, { method: "POST" });
  },
  async cancelEdgar(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/edgar/${jobId}/cancel`, token, { method: "POST" });
  },
  async getActiveEdgar(token: string) {
    return apiFetch<any>("/api/admin/edgar/active", token);
  },
  async getEdgarStartups(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/edgar/${jobId}/startups`, token);
  },
  async getEdgarFilings(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/edgar/${jobId}/filings`, token);
  },
  async getEdgarLog(token: string, jobId: string, page?: number) {
    const qs = page ? `?page=${page}` : "";
    return apiFetch<any>(`/api/admin/edgar/${jobId}/log${qs}`, token);
  },

  // Investors
  startInvestorBatch: (token: string) =>
    apiFetch<{ id: string; status: string }>("/api/admin/investors/batch", token, {
      method: "POST",
    }),

  pauseInvestorBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/batch/${jobId}/pause`, token, {
      method: "PUT",
    }),

  resumeInvestorBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/batch/${jobId}/resume`, token, {
      method: "PUT",
    }),

  getInvestorBatchStatus: (token: string) =>
    apiFetch<InvestorBatchStatus | null>("/api/admin/investors/batch/status", token),

  getInvestors: (token: string, params?: {
    q?: string;
    stage_focus?: string;
    sector_focus?: string;
    location?: string;
    page?: number;
    per_page?: number;
    sort?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.stage_focus) sp.set("stage_focus", params.stage_focus);
    if (params?.sector_focus) sp.set("sector_focus", params.sector_focus);
    if (params?.location) sp.set("location", params.location);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.per_page) sp.set("per_page", String(params.per_page));
    if (params?.sort) sp.set("sort", params.sort);
    const qs = sp.toString();
    return apiFetch<InvestorListResponse>(`/api/admin/investors${qs ? `?${qs}` : ""}`, token);
  },

  deleteInvestor: (token: string, investorId: string) =>
    apiFetch<{ ok: boolean }>(`/api/admin/investors/${investorId}`, token, {
      method: "DELETE",
    }),

  // Feedback
  getFeedbackList: (token: string, params?: {
    page?: number;
    status?: string;
    category?: string;
    severity?: string;
    area?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.page) sp.set("page", String(params.page));
    if (params?.status) sp.set("status", params.status);
    if (params?.category) sp.set("category", params.category);
    if (params?.severity) sp.set("severity", params.severity);
    if (params?.area) sp.set("area", params.area);
    const qs = sp.toString();
    return apiFetch<FeedbackListResponse>(`/api/admin/feedback${qs ? `?${qs}` : ""}`, token);
  },

  getFeedbackDetail: (token: string, id: string) =>
    apiFetch<FeedbackItem>(`/api/admin/feedback/${id}`, token),

  // Investor Rankings
  startRankingBatch: (token: string) =>
    apiFetch<{ id: string; status: string }>("/api/admin/investors/rankings/batch", token, {
      method: "POST",
    }),

  pauseRankingBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/rankings/batch/${jobId}/pause`, token, {
      method: "PUT",
    }),

  resumeRankingBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/rankings/batch/${jobId}/resume`, token, {
      method: "PUT",
    }),

  getRankingBatchStatus: (token: string) =>
    apiFetch<RankingBatchStatus | null>("/api/admin/investors/rankings/batch/status", token),

  getRankedInvestors: (token: string, params?: {
    sort?: string;
    order?: string;
    q?: string;
    min_score?: number;
    page?: number;
    per_page?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.sort) sp.set("sort", params.sort);
    if (params?.order) sp.set("order", params.order);
    if (params?.q) sp.set("q", params.q);
    if (params?.min_score !== undefined) sp.set("min_score", String(params.min_score));
    if (params?.page) sp.set("page", String(params.page));
    if (params?.per_page) sp.set("per_page", String(params.per_page));
    const qs = sp.toString();
    return apiFetch<RankedInvestorListResponse>(`/api/admin/investors/rankings${qs ? `?${qs}` : ""}`, token);
  },

  rescoreInvestor: (token: string, investorId: string) =>
    apiFetch<{ ok: boolean; message: string }>(`/api/admin/investors/rankings/${investorId}/rescore`, token, {
      method: "POST",
    }),
};
