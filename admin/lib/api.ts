import type {
  AdminUser,
  ApprovedExpert,
  Assignment,
  DDTemplate,
  Dimension,
  ExpertApplication,
  PipelineStartup,
  StartupDetail,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  updateStartup: (token: string, id: string, body: Record<string, unknown>) =>
    apiFetch<StartupDetail>(`/api/admin/startups/${id}`, token, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

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

  createTemplate: (token: string, body: { name: string; description?: string; dimensions: { dimension_name: string; weight: number; sort_order: number }[] }) =>
    apiFetch<DDTemplate>("/api/admin/dd-templates", token, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateTemplate: (token: string, id: string, body: { name: string; description?: string; dimensions: { dimension_name: string; weight: number; sort_order: number }[] }) =>
    apiFetch<DDTemplate>(`/api/admin/dd-templates/${id}`, token, {
      method: "PUT",
      body: JSON.stringify(body),
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
};
