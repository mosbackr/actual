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
    apiFetch<{ id: string; email: string; name: string; role: string }>(
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
};
