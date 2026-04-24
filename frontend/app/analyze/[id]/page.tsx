"use client";

import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ConfirmModal } from "@/components/Modal";
import type { AnalysisDetail, AnalysisReportFull, InvestmentMemo, ToolCallItem } from "@/lib/types";

const AGENT_LABELS: Record<string, string> = {
  problem_solution: "Problem & Solution",
  market_tam: "Market & TAM",
  traction: "Traction",
  technology_ip: "Technology & IP",
  competition_moat: "Competition & Moat",
  team: "Team",
  gtm_business_model: "GTM & Business Model",
  financials_fundraising: "Financials & Fundraising",
};

function ScoreBadge({ score, size = "sm" }: { score: number | null; size?: "sm" | "lg" }) {
  if (score === null) return null;
  const color = score >= 70 ? "text-score-high" : score >= 40 ? "text-score-mid" : "text-score-low";
  const bg = score >= 70 ? "bg-score-high/10" : score >= 40 ? "bg-score-mid/10" : "bg-score-low/10";
  const textSize = size === "lg" ? "text-3xl" : "text-sm";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded font-medium tabular-nums ${bg} ${color} ${textSize}`}>
      {Math.round(score)}
    </span>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "complete") return <span className="text-score-high">&#10003;</span>;
  if (status === "running") return <span className="animate-spin inline-block w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full" />;
  if (status === "failed") return <span className="text-score-low">&times;</span>;
  return <span className="text-text-tertiary">&mdash;</span>;
}

const TOOL_LABELS: Record<string, string> = {
  perplexity_search: "Perplexity Search",
  db_search_startups: "DB: Startups",
  db_get_analysis: "DB: Analysis",
  db_list_experts: "DB: Experts",
};

const AGENT_COLORS: Record<string, string> = {
  problem_solution: "bg-blue-100 text-blue-700",
  market_tam: "bg-emerald-100 text-emerald-700",
  traction: "bg-amber-100 text-amber-700",
  technology_ip: "bg-purple-100 text-purple-700",
  competition_moat: "bg-red-100 text-red-700",
  team: "bg-cyan-100 text-cyan-700",
  gtm_business_model: "bg-orange-100 text-orange-700",
  financials_fundraising: "bg-pink-100 text-pink-700",
};

function ActivityLog({ toolCalls, open, onToggle }: { toolCalls: ToolCallItem[]; open: boolean; onToggle: () => void }) {
  if (toolCalls.length === 0) return null;

  return (
    <div className="mt-6 rounded border border-border bg-surface">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-text-primary hover:bg-bg-secondary/50 transition"
      >
        <span>Activity Log ({toolCalls.length} tool calls)</span>
        <span className="text-text-tertiary text-xs">{open ? "\u25B2" : "\u25BC"}</span>
      </button>
      {open && (
        <div className="border-t border-border max-h-96 overflow-y-auto divide-y divide-border">
          {toolCalls.map((tc) => (
            <ToolCallEntry key={tc.id} tc={tc} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolCallEntry({ tc }: { tc: ToolCallItem }) {
  const [expanded, setExpanded] = useState(false);
  const agentLabel = AGENT_LABELS[tc.agent_type] || tc.agent_type;
  const toolLabel = TOOL_LABELS[tc.tool_name] || tc.tool_name;
  const agentColor = AGENT_COLORS[tc.agent_type] || "bg-gray-100 text-gray-700";
  const queryText = (tc.input?.query as string) || JSON.stringify(tc.input);

  return (
    <div className="px-4 py-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${agentColor}`}>
          {agentLabel}
        </span>
        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-border text-text-secondary">
          {toolLabel}
        </span>
        <span className="text-xs text-text-tertiary font-mono truncate max-w-xs" title={queryText}>
          {queryText}
        </span>
        <span className="ml-auto text-[10px] text-text-tertiary tabular-nums">
          {tc.duration_ms != null ? `${(tc.duration_ms / 1000).toFixed(1)}s` : ""}
        </span>
      </div>
      {tc.output && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] text-accent hover:text-accent-hover mt-1"
        >
          {expanded ? "Hide output" : "Show output"}
        </button>
      )}
      {expanded && tc.output && (
        <pre className="mt-1 text-[10px] text-text-tertiary bg-bg-secondary rounded p-2 max-h-40 overflow-y-auto whitespace-pre-wrap">
          {typeof tc.output === "object" ? JSON.stringify(tc.output, null, 2) : String(tc.output)}
        </pre>
      )}
    </div>
  );
}

export default function AnalysisResultPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [reports, setReports] = useState<AnalysisReportFull[]>([]);
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [memo, setMemo] = useState<InvestmentMemo | null>(null);
  const [memoLoading, setMemoLoading] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCallItem[]>([]);
  const [logOpen, setLogOpen] = useState(false);
  const lastToolCallTs = useRef<string | undefined>(undefined);

  const fetchData = useCallback(async () => {
    if (!token || !id) return;
    try {
      const data = await api.getAnalysis(token, id);
      setAnalysis(data);

      if (data.status === "complete" || data.status === "failed") {
        const rData = await api.getAnalysisReports(token, id);
        setReports(rData.items || []);
      }
    } catch {
      // silent
    }
    setLoading(false);
  }, [token, id]);

  const fetchMemo = useCallback(async () => {
    if (!token || !id) return;
    try {
      const m = await api.getMemo(token, id);
      setMemo(m);
    } catch {
      // 404 = no memo yet, that's fine
      setMemo(null);
    }
  }, [token, id]);

  const fetchToolCalls = useCallback(async () => {
    if (!token || !id) return;
    try {
      const data = await api.getToolCalls(token, id, lastToolCallTs.current);
      if (data.tool_calls.length > 0) {
        const newest = data.tool_calls[data.tool_calls.length - 1];
        if (newest.created_at) lastToolCallTs.current = newest.created_at;
        setToolCalls((prev) => {
          const existingIds = new Set(prev.map((tc) => tc.id));
          const newCalls = data.tool_calls.filter((tc) => !existingIds.has(tc.id));
          return [...prev, ...newCalls];
        });
      }
    } catch {
      // silent
    }
  }, [token, id]);

  useEffect(() => {
    fetchData();
    fetchMemo();
    fetchToolCalls();
  }, [fetchData, fetchMemo, fetchToolCalls]);

  useEffect(() => {
    if (!analysis) return;
    if (analysis.status === "complete" || analysis.status === "failed") return;
    const timer = setInterval(fetchData, 3000);
    return () => clearInterval(timer);
  }, [analysis?.status, fetchData]);

  // Poll memo status while generating
  useEffect(() => {
    if (!memo) return;
    if (["complete", "failed"].includes(memo.status)) return;
    const timer = setInterval(fetchMemo, 3000);
    return () => clearInterval(timer);
  }, [memo?.status, fetchMemo]);

  // Poll tool calls while analysis is running
  useEffect(() => {
    if (!analysis) return;
    if (analysis.status === "complete" || analysis.status === "failed") {
      fetchToolCalls();
      return;
    }
    const timer = setInterval(fetchToolCalls, 3000);
    return () => clearInterval(timer);
  }, [analysis?.status, fetchToolCalls]);

  async function handleGenerateMemo() {
    if (!token || !id) return;
    setMemoLoading(true);
    try {
      await api.generateMemo(token, id);
      await fetchMemo();
    } catch {
      // ignore — user may get 409 if already generating
    }
    setMemoLoading(false);
  }

  async function handleRegenerateMemo() {
    if (!token || !id) return;
    setMemoLoading(true);
    try {
      await api.regenerateMemo(token, id);
      await fetchMemo();
    } catch {
      // ignore
    }
    setMemoLoading(false);
  }

  async function handleDownload(format: "pdf" | "docx") {
    if (!token || !id || !analysis) return;
    const res = await fetch(api.getMemoDownloadUrl(id, format), {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `investment-memo-${analysis.company_name}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading || !analysis) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  const isRunning = !["complete", "failed"].includes(analysis.status);
  const completedReports = analysis.reports?.filter((r) => r.status === "complete") || [];
  const progress = analysis.reports ? completedReports.length : 0;

  // PROGRESS VIEW
  if (isRunning) {
    return (
      <div className="max-w-2xl mx-auto">
        <h1 className="font-serif text-2xl text-text-primary mb-2">{analysis.company_name}</h1>
        <p className="text-text-tertiary text-sm mb-6">
          {analysis.status === "extracting" ? "Extracting text from documents..." :
           analysis.status === "enriching" ? "Creating public profile..." :
           "Running analysis agents..."}
        </p>

        {/* Progress bar */}
        <div className="w-full h-2 bg-border rounded-full mb-6 overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-500"
            style={{ width: `${(progress / 8) * 100}%` }}
          />
        </div>

        {/* Agent status list */}
        <div className="rounded border border-border bg-surface divide-y divide-border">
          {Object.entries(AGENT_LABELS).map(([key, label]) => {
            const report = analysis.reports?.find((r) => r.agent_type === key);
            const status = report?.status || "pending";
            return (
              <div key={key} className="flex items-center justify-between px-4 py-3">
                <span className={`text-sm ${status === "running" ? "text-accent font-medium" : status === "complete" ? "text-text-primary" : "text-text-tertiary"}`}>
                  {label}
                </span>
                <div className="flex items-center gap-2">
                  {report?.score !== null && report?.score !== undefined && (
                    <ScoreBadge score={report.score} />
                  )}
                  <StatusIcon status={status} />
                </div>
              </div>
            );
          })}
        </div>
        <ActivityLog toolCalls={toolCalls} open={logOpen} onToggle={() => setLogOpen(!logOpen)} />
      </div>
    );
  }

  // FAILED VIEW
  if (analysis.status === "failed") {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <h1 className="font-serif text-2xl text-text-primary mb-2">{analysis.company_name}</h1>
        <p className="text-score-low mb-4">Analysis failed</p>
        <p className="text-text-tertiary text-sm">{analysis.error || "An unexpected error occurred"}</p>
        <Link href="/analyze" className="inline-block mt-6 px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition">
          Try Again
        </Link>
      </div>
    );
  }

  // RESULTS VIEW
  const tabs = ["overview", ...Object.keys(AGENT_LABELS)];
  const activeReport = reports.find((r) => r.agent_type === activeTab);
  const memoGenerating = memo && ["pending", "researching", "generating", "formatting"].includes(memo.status);

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-serif text-2xl text-text-primary">{analysis.company_name}</h1>
          <p className="text-text-tertiary text-xs mt-1">
            Analyzed {analysis.completed_at ? new Date(analysis.completed_at).toLocaleDateString() : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {analysis.status === "complete" && !memo && !memoLoading && (
            <button
              onClick={handleGenerateMemo}
              className="px-3 py-1.5 text-xs font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
            >
              Generate Investment Memo
            </button>
          )}
          {analysis.status === "complete" && !memo && memoLoading && (
            <span className="flex items-center gap-1.5 text-xs text-text-tertiary">
              <span className="animate-spin inline-block w-3 h-3 border border-accent/30 border-t-accent rounded-full" />
              Generating Investment Memo
            </span>
          )}
          {memoGenerating && (
            <span className="flex items-center gap-1.5 text-xs text-text-tertiary">
              <span className="animate-spin inline-block w-3 h-3 border border-accent/30 border-t-accent rounded-full" />
              Generating Investment Memo
            </span>
          )}
          {memo?.status === "complete" && (
            <button
              onClick={() => setActiveTab("memo")}
              className={`text-xs font-medium transition ${activeTab === "memo" ? "text-accent" : "text-accent/70 hover:text-accent"}`}
            >
              Investment Memo
            </button>
          )}
          {memo?.status === "failed" && (
            <button
              onClick={handleRegenerateMemo}
              disabled={memoLoading}
              className="text-xs text-score-low hover:text-score-low/80"
            >
              Memo Failed - Retry
            </button>
          )}
          <Link href="/analyze/history" className="text-xs text-text-tertiary hover:text-text-secondary">
            History
          </Link>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="text-xs text-score-low hover:text-score-low/80"
          >
            Delete
          </button>
          <ConfirmModal
            open={showDeleteConfirm}
            onClose={() => setShowDeleteConfirm(false)}
            onConfirm={async () => {
              await api.deleteAnalysis(token, id);
              router.push("/analyze/history");
            }}
            title="Delete Analysis"
            message="Are you sure you want to delete this analysis? This action cannot be undone."
            confirmLabel="Delete"
            destructive
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 overflow-x-auto border-b border-border mb-6">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition -mb-px ${
              activeTab === t
                ? "border-accent text-accent"
                : "border-transparent text-text-tertiary hover:text-text-secondary"
            }`}
          >
            {t === "overview" ? "Overview" : AGENT_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {activeTab === "overview" && (
        <div>
          {/* Score + metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Overall Score</p>
              <ScoreBadge score={analysis.overall_score} size="lg" />
            </div>
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Fundraising Likelihood</p>
              <p className="text-xl font-medium text-text-primary tabular-nums">
                {analysis.fundraising_likelihood != null ? `${Math.round(analysis.fundraising_likelihood)}%` : "\u2014"}
              </p>
            </div>
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Recommended Raise</p>
              <p className="text-lg font-medium text-text-primary">{analysis.recommended_raise || "\u2014"}</p>
            </div>
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Exit Likelihood</p>
              <p className="text-xl font-medium text-text-primary tabular-nums">
                {analysis.exit_likelihood != null ? `${Math.round(analysis.exit_likelihood)}%` : "\u2014"}
              </p>
            </div>
          </div>

          {/* Valuation + Exit projections */}
          {(analysis.estimated_valuation || analysis.expected_exit_value || analysis.expected_exit_timeline) && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              {analysis.estimated_valuation && (
                <div className="rounded border border-accent/30 bg-accent/5 p-4 text-center">
                  <p className="text-xs text-text-tertiary mb-1">Estimated Valuation</p>
                  <p className="text-lg font-medium text-accent">{analysis.estimated_valuation}</p>
                </div>
              )}
              <div className="rounded border border-border bg-surface p-4 text-center">
                <p className="text-xs text-text-tertiary mb-1">Expected Exit Value</p>
                <p className="text-lg font-medium text-text-primary">{analysis.expected_exit_value || "\u2014"}</p>
              </div>
              <div className="rounded border border-border bg-surface p-4 text-center">
                <p className="text-xs text-text-tertiary mb-1">Expected Timeline</p>
                <p className="text-lg font-medium text-text-primary">{analysis.expected_exit_timeline || "\u2014"}</p>
              </div>
            </div>
          )}

          {/* Valuation Justification */}
          {analysis.valuation_justification && (
            <div className="rounded border border-border bg-surface p-4 mb-6">
              <h3 className="text-sm font-medium text-text-primary mb-2">Valuation Justification</h3>
              <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">{analysis.valuation_justification}</p>
            </div>
          )}

          {/* Executive summary */}
          {analysis.executive_summary && (
            <div className="rounded border border-border bg-surface p-4 mb-6">
              <h3 className="text-sm font-medium text-text-primary mb-2">Executive Summary</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{analysis.executive_summary}</p>
            </div>
          )}

          {/* Technical Expert Review */}
          {analysis.technical_expert_review && (
            <div className="rounded border border-border bg-surface p-4 mb-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-text-primary">Technical Expert Review</h3>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                    analysis.technical_expert_review.technical_feasibility === "Proven" ? "bg-green-100 text-green-700" :
                    analysis.technical_expert_review.technical_feasibility === "Plausible" ? "bg-blue-100 text-blue-700" :
                    analysis.technical_expert_review.technical_feasibility === "Speculative" ? "bg-yellow-100 text-yellow-700" :
                    "bg-red-100 text-red-700"
                  }`}>
                    {analysis.technical_expert_review.technical_feasibility}
                  </span>
                  <span className="text-xs text-text-tertiary">TRL {analysis.technical_expert_review.trl_level}/9</span>
                </div>
              </div>
              <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line mb-3">
                {analysis.technical_expert_review.scientific_consensus}
              </p>
              {analysis.technical_expert_review.red_flags.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-medium text-score-low mb-1">Red Flags</p>
                  <ul className="space-y-1">
                    {analysis.technical_expert_review.red_flags.map((flag, i) => (
                      <li key={i} className="text-xs text-score-low flex gap-1.5">
                        <span>&#9888;</span> {flag}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-sm text-text-secondary italic">{analysis.technical_expert_review.verdict}</p>
            </div>
          )}

          {/* Score cards grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(AGENT_LABELS).map(([key, label]) => {
              const report = reports.find((r) => r.agent_type === key);
              return (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className="rounded border border-border bg-surface p-4 text-left hover:border-accent/50 transition"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-text-primary">{label}</span>
                    <ScoreBadge score={report?.score ?? null} />
                  </div>
                  <p className="text-xs text-text-secondary line-clamp-2">{report?.summary || "\u2014"}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Memo view */}
      {activeTab === "memo" && memo?.status === "complete" && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <button
              onClick={() => handleDownload("pdf")}
              className="px-3 py-1.5 text-xs font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
            >
              Download PDF
            </button>
            <button
              onClick={() => handleDownload("docx")}
              className="px-3 py-1.5 text-xs font-medium rounded border border-border text-text-primary hover:border-accent/50 transition"
            >
              Download DOCX
            </button>
            <button
              onClick={handleRegenerateMemo}
              disabled={memoLoading}
              className="text-xs text-text-tertiary hover:text-text-secondary ml-auto"
            >
              Regenerate
            </button>
          </div>
          {memo.content && (
            <div className="rounded border border-border bg-surface p-6 text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
              {memo.content}
            </div>
          )}
        </div>
      )}

      {/* Agent report tabs */}
      {activeTab !== "overview" && activeTab !== "memo" && activeReport && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <ScoreBadge score={activeReport.score} size="lg" />
            <p className="text-sm text-text-secondary">{activeReport.summary}</p>
          </div>

          {activeReport.key_findings && activeReport.key_findings.length > 0 && (
            <div className="rounded border border-border bg-surface p-4 mb-4">
              <h3 className="text-sm font-medium text-text-primary mb-2">Key Findings</h3>
              <ul className="space-y-1">
                {activeReport.key_findings.map((f, i) => (
                  <li key={i} className="text-sm text-text-secondary flex gap-2">
                    <span className="text-accent">&#x2022;</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {activeReport.report && (
            <div className="rounded border border-border bg-surface p-4 text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
              {activeReport.report}
            </div>
          )}

          {activeReport.status === "failed" && (
            <div className="rounded border border-score-low/20 bg-score-low/10 p-4 text-score-low text-sm">
              Agent failed: {activeReport.error || "Unknown error"}
            </div>
          )}
        </div>
      )}

      {/* Activity Log */}
      <ActivityLog toolCalls={toolCalls} open={logOpen} onToggle={() => setLogOpen(!logOpen)} />
    </div>
  );
}
