"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import type { FeedbackItem, FeedbackListResponse } from "@/lib/types";

const CATEGORIES = ["bug", "feature_request", "ux_issue", "performance", "general"];
const SEVERITIES = ["critical", "high", "medium", "low"];
const STATUSES = ["active", "complete", "abandoned"];

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};

const CATEGORY_LABELS: Record<string, string> = {
  bug: "Bug",
  feature_request: "Feature",
  ux_issue: "UX Issue",
  performance: "Performance",
  general: "General",
};

export default function FeedbackPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  const [data, setData] = useState<FeedbackListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<FeedbackItem | null>(null);
  const [filters, setFilters] = useState<{
    status?: string;
    category?: string;
    severity?: string;
  }>({});
  const [page, setPage] = useState(1);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const result = await adminApi.getFeedbackList(token, { page, ...filters });
      setData(result);
    } catch (e) {
      console.error("Failed to load feedback", e);
    }
    setLoading(false);
  }, [token, page, filters]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSelectItem = async (item: FeedbackItem) => {
    if (!token) return;
    try {
      const detail = await adminApi.getFeedbackDetail(token, item.id);
      setSelected(detail);
    } catch {
      setSelected(item);
    }
  };

  if (selected) {
    return (
      <div className="p-6">
        <button
          onClick={() => setSelected(null)}
          className="mb-4 text-sm text-text-secondary hover:text-text-primary transition"
        >
          &larr; Back to list
        </button>

        <div className="space-y-6">
          {/* Summary */}
          <div className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-lg font-medium text-text-primary mb-2">Summary</h2>
            <p className="text-text-secondary text-sm">{selected.summary || "No summary available"}</p>
          </div>

          {/* Tags */}
          <div className="flex flex-wrap gap-2">
            {selected.category && (
              <span className="rounded-full bg-blue-100 text-blue-700 px-3 py-1 text-xs font-medium">
                {CATEGORY_LABELS[selected.category] || selected.category}
              </span>
            )}
            {selected.severity && (
              <span className={`rounded-full px-3 py-1 text-xs font-medium ${SEVERITY_COLORS[selected.severity] || "bg-gray-100 text-gray-700"}`}>
                {selected.severity}
              </span>
            )}
            {selected.area && (
              <span className="rounded-full bg-purple-100 text-purple-700 px-3 py-1 text-xs font-medium">
                {selected.area}
              </span>
            )}
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${
              selected.status === "complete" ? "bg-green-100 text-green-700"
              : selected.status === "abandoned" ? "bg-gray-100 text-gray-500"
              : "bg-yellow-100 text-yellow-700"
            }`}>
              {selected.status}
            </span>
          </div>

          {/* Recommendations */}
          {selected.recommendations && selected.recommendations.length > 0 && (
            <div className="rounded-lg border border-border bg-surface p-5">
              <h2 className="text-lg font-medium text-text-primary mb-3">AI Recommendations</h2>
              <div className="space-y-3">
                {selected.recommendations
                  .sort((a, b) => a.priority - b.priority)
                  .map((rec, i) => (
                    <div key={i} className="flex gap-3">
                      <span className="flex-shrink-0 flex items-center justify-center h-6 w-6 rounded-full bg-accent/10 text-accent text-xs font-medium">
                        {rec.priority}
                      </span>
                      <div>
                        <p className="text-sm font-medium text-text-primary">{rec.title}</p>
                        <p className="text-sm text-text-secondary mt-0.5">{rec.description}</p>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-lg font-medium text-text-primary mb-2">Details</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-text-tertiary">User:</span>{" "}
                <span className="text-text-primary">{selected.user_name || "Unknown"}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Email:</span>{" "}
                <span className="text-text-primary">{selected.user_email || "\u2014"}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Page:</span>{" "}
                <span className="text-text-primary">{selected.page_url || "\u2014"}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Date:</span>{" "}
                <span className="text-text-primary">
                  {selected.created_at ? new Date(selected.created_at).toLocaleString() : "\u2014"}
                </span>
              </div>
            </div>
          </div>

          {/* Transcript */}
          {selected.transcript && selected.transcript.length > 0 && (
            <div className="rounded-lg border border-border bg-surface p-5">
              <h2 className="text-lg font-medium text-text-primary mb-3">Conversation</h2>
              <div className="space-y-3">
                {selected.transcript.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                        msg.role === "user"
                          ? "bg-accent/10 text-text-primary"
                          : "bg-surface-alt text-text-primary"
                      }`}
                    >
                      <p className="text-xs text-text-tertiary mb-1">
                        {msg.role === "user" ? "User" : "Agent"}
                      </p>
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-serif text-text-primary mb-6">User Feedback</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <select
          value={filters.status || ""}
          onChange={(e) => { setFilters((f) => ({ ...f, status: e.target.value || undefined })); setPage(1); }}
          className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-text-primary"
        >
          <option value="">All Statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={filters.category || ""}
          onChange={(e) => { setFilters((f) => ({ ...f, category: e.target.value || undefined })); setPage(1); }}
          className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-text-primary"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{CATEGORY_LABELS[c] || c}</option>
          ))}
        </select>
        <select
          value={filters.severity || ""}
          onChange={(e) => { setFilters((f) => ({ ...f, severity: e.target.value || undefined })); setPage(1); }}
          className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-text-primary"
        >
          <option value="">All Severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <p className="text-text-tertiary text-sm">Loading...</p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-text-tertiary text-sm">No feedback found.</p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-alt text-left">
                  <th className="px-4 py-2 font-medium text-text-secondary">Date</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">User</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Category</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Severity</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Area</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Summary</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => handleSelectItem(item)}
                    className="border-b border-border hover:bg-hover-row cursor-pointer transition"
                  >
                    <td className="px-4 py-2 text-text-tertiary whitespace-nowrap">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2 text-text-primary">
                      {item.user_name || item.user_email || "Unknown"}
                    </td>
                    <td className="px-4 py-2">
                      {item.category && (
                        <span className="rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-xs">
                          {CATEGORY_LABELS[item.category] || item.category}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {item.severity && (
                        <span className={`rounded-full px-2 py-0.5 text-xs ${SEVERITY_COLORS[item.severity] || "bg-gray-100 text-gray-700"}`}>
                          {item.severity}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-text-secondary text-xs">
                      {item.area || "\u2014"}
                    </td>
                    <td className="px-4 py-2 text-text-secondary max-w-xs truncate">
                      {item.summary || "\u2014"}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`text-xs ${
                        item.status === "complete" ? "text-green-600"
                        : item.status === "abandoned" ? "text-gray-400"
                        : "text-yellow-600"
                      }`}>
                        {item.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data.pages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-text-tertiary">
                Page {data.page} of {data.pages} ({data.total} total)
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 text-sm rounded border border-border hover:bg-hover-row disabled:opacity-40 transition"
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={page === data.pages}
                  className="px-3 py-1 text-sm rounded border border-border hover:bg-hover-row disabled:opacity-40 transition"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
