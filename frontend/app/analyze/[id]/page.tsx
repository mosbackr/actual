"use client";

import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ConfirmModal } from "@/components/Modal";
import type { AnalysisDetail, AnalysisReportFull } from "@/lib/types";

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

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (!analysis) return;
    if (analysis.status === "complete" || analysis.status === "failed") return;
    const timer = setInterval(fetchData, 3000);
    return () => clearInterval(timer);
  }, [analysis?.status, fetchData]);

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

          {/* Exit projections */}
          {(analysis.expected_exit_value || analysis.expected_exit_timeline) && (
            <div className="grid grid-cols-2 gap-4 mb-6">
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

          {/* Executive summary */}
          {analysis.executive_summary && (
            <div className="rounded border border-border bg-surface p-4 mb-6">
              <h3 className="text-sm font-medium text-text-primary mb-2">Executive Summary</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{analysis.executive_summary}</p>
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

      {/* Agent report tabs */}
      {activeTab !== "overview" && activeReport && (
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
    </div>
  );
}
