import type {
  AnalystConversationSummary,
  AnalystConversationDetail,
  AnalystReportSummary,
  AnalystSharedConversation,
  NotificationList,
  ReportListItem,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || `API error: ${res.status} ${res.statusText}`);
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

  getToolCalls: (token: string, id: string, since?: string) => {
    const params = new URLSearchParams();
    if (since) params.set("since", since);
    params.set("include_output", "true");
    const qs = params.toString();
    return apiFetch<{ tool_calls: import("./types").ToolCallItem[] }>(
      `/api/analyze/${id}/tool-calls${qs ? `?${qs}` : ""}`,
      { headers: authHeaders(token) }
    );
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

  streamMessage(token: string, conversationId: string, content: string, files?: File[]) {
    const url = `${API_URL}/api/analyst/conversations/${conversationId}/messages`;
    const formData = new FormData();
    formData.append("content", content);
    if (files) {
      for (const file of files) {
        formData.append("files", file);
      }
    }
    return fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });
  },

  async createReport(token: string, conversationId: string, format: "docx" | "xlsx" | "pdf" | "pptx", title?: string) {
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

  // ── Billing ───────────────────────────────────────────────────────────

  async createCheckoutSession(token: string, tier: string) {
    return apiFetch<{ url: string }>("/api/billing/checkout", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ tier }),
    });
  },

  async createPortalSession(token: string) {
    return apiFetch<{ url: string }>("/api/billing/portal", {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  async getBillingStatus(token: string) {
    return apiFetch<import("./types").BillingStatus>("/api/billing/status", {
      headers: authHeaders(token),
    });
  },

  // ── Notifications ───────────────────────────────────────────────────

  async getNotifications(token: string) {
    return apiFetch<NotificationList>("/api/notifications", {
      headers: authHeaders(token),
    });
  },

  async markNotificationRead(token: string, id: string) {
    return apiFetch<{ success: boolean }>(`/api/notifications/${id}/read`, {
      method: "PATCH",
      headers: authHeaders(token),
    });
  },

  async markAllNotificationsRead(token: string) {
    return apiFetch<{ success: boolean }>("/api/notifications/read-all", {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  async listAllReports(token: string) {
    return apiFetch<{ items: ReportListItem[] }>("/api/analyst/reports", {
      headers: authHeaders(token),
    });
  },

  // ── Investment Memo ────────────────────────────────────────────────

  async generateMemo(token: string, analysisId: string) {
    return apiFetch<{ id: string; status: string }>(
      `/api/analyze/${analysisId}/memo`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async regenerateMemo(token: string, analysisId: string) {
    return apiFetch<{ id: string; status: string }>(
      `/api/analyze/${analysisId}/memo/regenerate`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getMemo(token: string, analysisId: string) {
    return apiFetch<import("./types").InvestmentMemo>(
      `/api/analyze/${analysisId}/memo`,
      { headers: authHeaders(token) }
    );
  },

  getMemoDownloadUrl(analysisId: string, format: "pdf" | "docx") {
    return `${API_URL}/api/analyze/${analysisId}/memo/download/${format}`;
  },

  // ── Investor FAQ ───────────────────────────────────────────────────

  async generateAnalysisFaq(token: string, analysisId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/analyze/${analysisId}/faq`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getAnalysisFaq(token: string, analysisId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/analyze/${analysisId}/faq`,
      { headers: authHeaders(token) }
    );
  },

  async generatePitchFaq(token: string, sessionId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/pitch-intelligence/${sessionId}/faq`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getPitchFaq(token: string, sessionId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/pitch-intelligence/${sessionId}/faq`,
      { headers: authHeaders(token) }
    );
  },

  // ── Watchlist ─────────────────────────────────────────────────────

  async getWatchlist(token: string, page = 1) {
    return apiFetch<import("./types").WatchlistResponse>(
      `/api/watchlist?page=${page}`,
      { headers: authHeaders(token) }
    );
  },

  async getWatchlistIds(token: string) {
    return apiFetch<{ ids: string[] }>("/api/watchlist/ids", {
      headers: authHeaders(token),
    });
  },

  async addToWatchlist(token: string, startupId: string) {
    return apiFetch<{ success: boolean }>("/api/watchlist", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ startup_id: startupId }),
    });
  },

  async removeFromWatchlist(token: string, startupId: string) {
    return apiFetch<{ success: boolean }>(`/api/watchlist/${startupId}`, {
      method: "DELETE",
      headers: authHeaders(token),
    });
  },

  // ── Pitch Intelligence ──────────────────────────────────────────────

  createPitchUpload: async (
    token: string,
    filename: string,
    contentType: string,
    title?: string,
    startupId?: string,
  ): Promise<{ id: string; upload_url: string; s3_key: string }> => {
    return apiFetch("/api/pitch-intelligence/upload", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({
        filename,
        content_type: contentType,
        title: title || null,
        startup_id: startupId || null,
      }),
    });
  },

  submitPitchTranscript: async (
    token: string,
    text: string,
    title?: string,
  ): Promise<{ id: string; status: string; speakers: { id: string; name: string }[] }> => {
    return apiFetch("/api/pitch-intelligence/transcript", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ text, title: title || null }),
    });
  },

  submitVideoUrl: async (
    token: string,
    url: string,
    title?: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch("/api/pitch-intelligence/video-url", {
      method: "POST",
      headers: { ...authHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({ url, title }),
    });
  },

  completePitchUpload: async (token: string, sessionId: string): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/pitch-intelligence/${sessionId}/upload-complete`, {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  labelPitchSpeakers: async (
    token: string,
    sessionId: string,
    speakers: { speaker_id: string; name: string; role: string }[],
  ): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/pitch-intelligence/${sessionId}/speakers`, {
      method: "PUT",
      headers: authHeaders(token),
      body: JSON.stringify({ speakers }),
    });
  },

  getPitchSession: (token: string, sessionId: string): Promise<import("./types").PitchSessionDetail> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}`, {
      headers: authHeaders(token),
    }),

  getPitchStatus: (token: string, sessionId: string): Promise<import("./types").PitchStatusResponse> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}/status`, {
      headers: authHeaders(token),
    }),

  listPitchSessions: (token: string): Promise<{ items: import("./types").PitchSessionSummary[] }> =>
    apiFetch("/api/pitch-intelligence", {
      headers: authHeaders(token),
    }),

  deletePitchSession: async (token: string, sessionId: string): Promise<{ deleted: boolean }> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}`, {
      method: "DELETE",
      headers: authHeaders(token),
    }),

  getPitchTranscript: (token: string, sessionId: string): Promise<import("./types").PitchTranscript> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}/transcript`, {
      headers: authHeaders(token),
    }),

  // -- Zoom --

  async getZoomConnection(token: string) {
    return apiFetch<{ connected: boolean; zoom_email?: string; zoom_account_id?: string; connected_at?: string }>(
      "/api/zoom/connection",
      { headers: authHeaders(token) }
    );
  },

  async linkZoom(token: string, tempCode: string) {
    return apiFetch<{ ok: boolean; zoom_email: string }>(
      "/api/zoom/link",
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ temp_code: tempCode }),
      }
    );
  },

  async disconnectZoom(token: string) {
    return apiFetch<{ ok: boolean }>(
      "/api/zoom/connection",
      { method: "DELETE", headers: authHeaders(token) }
    );
  },

  async importZoomRecording(token: string, sessionId: string) {
    return apiFetch<{ ok: boolean; id: string }>(
      `/api/zoom/import/${sessionId}`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  // ── Feedback ─────────────────────────────────────────────────────────

  createFeedbackSession: async (
    token: string,
    pageUrl?: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch("/api/feedback/sessions", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ page_url: pageUrl || null }),
    });
  },

  sendFeedbackMessage(token: string, sessionId: string, content: string) {
    const url = `${API_URL}/api/feedback/sessions/${sessionId}/messages`;
    return fetch(url, {
      method: "POST",
      headers: {
        ...authHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content }),
    });
  },

  completeFeedbackSession: async (
    token: string,
    sessionId: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/feedback/sessions/${sessionId}/complete`, {
      method: "PATCH",
      headers: authHeaders(token),
    });
  },

  abandonFeedbackSession: async (
    token: string,
    sessionId: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/feedback/sessions/${sessionId}/abandon`, {
      method: "PATCH",
      headers: authHeaders(token),
    });
  },

  // ── Portfolio ──��──────────────────────────────────────────────────────

  async getPortfolio(token: string | null, investorId: string) {
    return apiFetch<{
      items: Array<{
        id: string;
        investor_id: string;
        startup_id: string | null;
        company_name: string;
        company_website: string | null;
        investment_date: string | null;
        round_stage: string | null;
        check_size: string | null;
        is_lead: boolean;
        board_seat: boolean;
        status: string;
        exit_type: string | null;
        exit_multiple: number | null;
        is_public: boolean;
        startup_slug: string | null;
        startup_logo_url: string | null;
        startup_stage: string | null;
      }>;
      is_owner: boolean;
    }>(`/api/investors/${investorId}/portfolio`, {
      headers: token ? authHeaders(token) : {},
    });
  },

  async addPortfolioCompany(
    token: string,
    investorId: string,
    body: {
      company_name: string;
      startup_id?: string;
      company_website?: string;
      investment_date?: string;
      round_stage?: string;
      check_size?: string;
      is_lead?: boolean;
      board_seat?: boolean;
      status?: string;
      is_public?: boolean;
    }
  ) {
    return apiFetch<Record<string, unknown>>(
      `/api/investors/${investorId}/portfolio`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
      }
    );
  },

  async updatePortfolioCompany(
    token: string,
    investorId: string,
    portfolioId: string,
    body: Record<string, unknown>
  ) {
    return apiFetch<Record<string, unknown>>(
      `/api/investors/${investorId}/portfolio/${portfolioId}`,
      {
        method: "PUT",
        headers: authHeaders(token),
        body: JSON.stringify(body),
      }
    );
  },

  async deletePortfolioCompany(token: string, investorId: string, portfolioId: string) {
    await fetch(`${API_URL}/api/investors/${investorId}/portfolio/${portfolioId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
    });
  },

  async claimInvestorProfile(token: string) {
    return apiFetch<{
      investor_id: string;
      firm_name: string;
      partner_name: string;
      already_claimed: boolean;
    }>("/api/investors/claim", {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  async getSuggestedPortfolio(token: string, investorId: string) {
    return apiFetch<{
      suggestions: Array<{
        company_name: string;
        matched_startup: {
          id: string;
          slug: string;
          name: string;
          logo_url: string | null;
          stage: string | null;
        } | null;
      }>;
    }>(`/api/investors/${investorId}/suggested-portfolio`, {
      headers: authHeaders(token),
    });
  },
};
