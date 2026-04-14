import type {
  AnalystConversationSummary,
  AnalystConversationDetail,
  AnalystReportSummary,
  AnalystSharedConversation,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export const api = {
  getStartups: (params?: URLSearchParams) =>
    apiFetch<import("./types").PaginatedStartups>(
      `/api/startups${params ? `?${params}` : ""}`
    ),

  getStartup: (slug: string) =>
    apiFetch<import("./types").StartupDetail>(`/api/startups/${slug}`),

  getIndustries: () =>
    apiFetch<import("./types").Industry[]>("/api/industries"),

  getStages: () =>
    apiFetch<import("./types").Stage[]>("/api/stages"),

  getMe: (token: string) =>
    apiFetch<{ id: string; email: string; name: string; role: string; avatar_url: string | null; ecosystem_role: string | null; region: string | null }>(
      "/api/me",
      { headers: authHeaders(token) }
    ),

  applyAsExpert: (token: string, body: {
    bio: string;
    years_experience: number;
    industry_ids: string[];
    skill_ids: string[];
  }) =>
    apiFetch<import("./types").ExpertApplication>("/api/experts/apply", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
    }),

  getMyApplication: (token: string) =>
    apiFetch<import("./types").ExpertApplication>(
      "/api/expert/applications/mine",
      { headers: authHeaders(token) }
    ),

  getReviews: (slug: string, reviewType?: string, token?: string) => {
    const params = reviewType ? `?review_type=${reviewType}` : "";
    return apiFetch<import("./types").Review[]>(
      `/api/startups/${slug}/reviews${params}`,
      token ? { headers: authHeaders(token) } : undefined,
    );
  },

  createReview: (token: string, slug: string, body: {
    overall_score: number;
    dimension_scores?: Record<string, number>;
    comment?: string;
  }) =>
    apiFetch<import("./types").Review>(`/api/startups/${slug}/reviews`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
    }),

  voteOnReview: (token: string, reviewId: string, voteType: "up" | "down") =>
    apiFetch<import("./types").Review>(`/api/reviews/${reviewId}/vote`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ vote_type: voteType }),
    }),

  getInsights: (params?: URLSearchParams) =>
    apiFetch<import("./insights-types").InsightsResponse>(
      `/api/insights${params ? `?${params}` : ""}`
    ),

  createAnalysis: async (token: string, formData: FormData): Promise<{ id: string; status: string }> => {
    const res = await fetch(`${API_URL}/api/analyze`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed: ${res.status}`);
    }
    return res.json();
  },

  listAnalyses: (token: string) =>
    apiFetch<{ items: import("./types").AnalysisListItem[] }>("/api/analyze", {
      headers: authHeaders(token),
    }),

  getAnalysis: (token: string, id: string) =>
    apiFetch<import("./types").AnalysisDetail>(`/api/analyze/${id}`, {
      headers: authHeaders(token),
    }),

  getAnalysisReports: (token: string, id: string) =>
    apiFetch<{ items: import("./types").AnalysisReportFull[] }>(`/api/analyze/${id}/reports`, {
      headers: authHeaders(token),
    }),

  deleteAnalysis: async (token: string, id: string) => {
    await apiFetch(`/api/analyze/${id}`, {
      method: "DELETE",
      headers: authHeaders(token),
    });
  },

  updateAnalysisConsent: async (token: string, id: string, publish_consent: boolean) => {
    await apiFetch(`/api/analyze/${id}`, {
      method: "PATCH",
      headers: authHeaders(token),
      body: JSON.stringify({ publish_consent }),
    });
  },

  resubmitAnalysis: async (token: string, id: string, formData: FormData): Promise<{ id: string; status: string }> => {
    const res = await fetch(`${API_URL}/api/analyze/${id}/resubmit`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Resubmit failed: ${res.status}`);
    }
    return res.json();
  },

  // ── Analyst ──────────────────────────────────────────────────────────

  async createConversation(token: string) {
    return apiFetch<{ id: string; title: string; is_free_conversation: boolean }>(
      "/api/analyst/conversations",
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async listConversations(token: string) {
    return apiFetch<{ items: AnalystConversationSummary[] }>(
      "/api/analyst/conversations",
      { headers: authHeaders(token) }
    );
  },

  async getConversation(token: string, id: string) {
    return apiFetch<AnalystConversationDetail>(
      `/api/analyst/conversations/${id}`,
      { headers: authHeaders(token) }
    );
  },

  async updateConversationTitle(token: string, id: string, title: string) {
    return apiFetch<{ ok: boolean }>(
      `/api/analyst/conversations/${id}`,
      {
        method: "PATCH",
        headers: { ...authHeaders(token), "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      }
    );
  },

  async deleteConversation(token: string, id: string) {
    return apiFetch<{ ok: boolean }>(
      `/api/analyst/conversations/${id}`,
      { method: "DELETE", headers: authHeaders(token) }
    );
  },

  streamMessage(token: string, conversationId: string, content: string) {
    const url = `${API_URL}/api/analyst/conversations/${conversationId}/messages`;
    return fetch(url, {
      method: "POST",
      headers: {
        ...authHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content }),
    });
  },

  async createReport(token: string, conversationId: string, format: "docx" | "xlsx", title?: string) {
    return apiFetch<{ id: string; status: string }>(
      `/api/analyst/conversations/${conversationId}/reports`,
      {
        method: "POST",
        headers: { ...authHeaders(token), "Content-Type": "application/json" },
        body: JSON.stringify({ format, title }),
      }
    );
  },

  async listReports(token: string) {
    return apiFetch<{ items: AnalystReportSummary[] }>(
      "/api/analyst/reports",
      { headers: authHeaders(token) }
    );
  },

  async getReportStatus(token: string, reportId: string) {
    return apiFetch<{ id: string; status: string; file_size_bytes: number | null; error: string | null }>(
      `/api/analyst/reports/${reportId}`,
      { headers: authHeaders(token) }
    );
  },

  getReportDownloadUrl(reportId: string) {
    return `${API_URL}/api/analyst/reports/${reportId}/download`;
  },

  async shareConversation(token: string, conversationId: string) {
    return apiFetch<{ share_token: string; url: string }>(
      `/api/analyst/conversations/${conversationId}/share`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getSharedConversation(shareToken: string) {
    return apiFetch<AnalystSharedConversation>(
      `/api/analyst/shared/${shareToken}`,
      {}
    );
  },
};
