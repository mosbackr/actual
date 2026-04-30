"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import type { AnalystConversationSummary, ReportListItem } from "@/lib/types";


interface Props {
  conversations: AnalystConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSuggestion: (prompt: string) => void;
  onOpenPrompts: () => void;
  isOpen: boolean;
  onToggle: () => void;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const FORMAT_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "DOCX",
  pptx: "PPTX",
  xlsx: "XLSX",
};

export function AnalystSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onSuggestion,
  onOpenPrompts,
  isOpen,
  onToggle,
}: Props) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [activeTab, setActiveTab] = useState<"conversations" | "reports">("conversations");
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [reportsLoaded, setReportsLoaded] = useState(false);

  const loadReports = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listAllReports(token);
      setReports(data.items);
    } catch {
      // silent
    } finally {
      setReportsLoaded(true);
    }
  }, [token]);

  // Load reports when tab switches to reports
  useEffect(() => {
    if (activeTab === "reports" && !reportsLoaded) {
      loadReports();
    }
  }, [activeTab, reportsLoaded, loadReports]);

  const handleReportClick = async (report: ReportListItem) => {
    if (report.status !== "complete" || !token) return;
    const url = api.getReportDownloadUrl(report.id);
    try {
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return;
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${report.conversation_title || report.title}.${report.format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      // silent
    }
  };

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={onToggle}
        className="md:hidden fixed top-20 left-3 z-30 p-2 rounded bg-surface border border-border text-text-secondary hover:text-text-primary"
        aria-label="Toggle sidebar"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Overlay for mobile */}
      {isOpen && (
        <div className="md:hidden fixed inset-0 bg-black/30 z-30" onClick={onToggle} />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:relative z-40 md:z-auto top-0 left-0 h-full w-64 bg-surface border-r border-border flex flex-col transition-transform md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* New button */}
        <div className="p-3 border-b border-border">
          <button
            onClick={onNew}
            className="w-full px-3 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            + New Conversation
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          <button
            onClick={() => setActiveTab("conversations")}
            className={`flex-1 px-3 py-2 text-xs font-medium transition ${
              activeTab === "conversations"
                ? "text-text-primary border-b-2 border-accent"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            Conversations
          </button>
          <button
            onClick={() => setActiveTab("reports")}
            className={`flex-1 px-3 py-2 text-xs font-medium transition ${
              activeTab === "reports"
                ? "text-text-primary border-b-2 border-accent"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            Reports
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === "conversations" ? (
            <>
              {conversations.length > 0 && (
                <div className="p-3">
                  <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-2">History</p>
                  <div className="space-y-0.5">
                    {conversations.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => onSelect(c.id)}
                        className={`w-full text-left px-2 py-1.5 rounded text-sm truncate transition ${
                          activeId === c.id
                            ? "bg-accent/10 text-accent"
                            : "text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                        }`}
                        title={c.title}
                      >
                        {c.title}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggestions */}
              <div className="p-3 border-t border-border">
                <button
                  onClick={onOpenPrompts}
                  className="w-full px-3 py-2 text-xs rounded border border-border text-text-tertiary hover:text-text-secondary hover:border-text-tertiary transition"
                >
                  Browse Suggested Prompts
                </button>
              </div>
            </>
          ) : (
            <div className="p-3">
              {!reportsLoaded ? (
                <p className="text-xs text-text-tertiary text-center py-4">Loading...</p>
              ) : reports.length === 0 ? (
                <p className="text-xs text-text-tertiary text-center py-4">No reports generated yet</p>
              ) : (
                <div className="space-y-1">
                  {reports.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => handleReportClick(r)}
                      className={`w-full text-left px-2 py-2 rounded transition ${
                        r.status === "complete"
                          ? "hover:bg-surface-alt cursor-pointer"
                          : "cursor-default opacity-70"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-accent/10 text-accent shrink-0">
                          {FORMAT_LABELS[r.format] || r.format.toUpperCase()}
                        </span>
                        <span className="text-sm text-text-secondary truncate flex-1">
                          {r.title}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 ml-8">
                        {r.status === "complete" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-score-high shrink-0" />
                        )}
                        {r.status === "generating" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse shrink-0" />
                        )}
                        {r.status === "failed" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-score-low shrink-0" />
                        )}
                        {r.status === "pending" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-text-tertiary shrink-0" />
                        )}
                        <span className="text-[10px] text-text-tertiary">
                          {timeAgo(r.created_at)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
