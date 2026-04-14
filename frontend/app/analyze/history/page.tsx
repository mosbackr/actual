"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AnalysisListItem } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  extracting: "Extracting",
  analyzing: "Analyzing",
  enriching: "Publishing",
  complete: "Complete",
  failed: "Failed",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-border text-text-tertiary",
  extracting: "bg-accent/10 text-accent",
  analyzing: "bg-accent/10 text-accent",
  enriching: "bg-accent/10 text-accent",
  complete: "bg-score-high/10 text-score-high",
  failed: "bg-score-low/10 text-score-low",
};

export default function AnalysisHistoryPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [analyses, setAnalyses] = useState<AnalysisListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api.listAnalyses(token).then((data) => {
      setAnalyses(data.items || []);
      setLoading(false);
    });
  }, [token]);

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-serif text-2xl text-text-primary">Analysis History</h1>
        <Link
          href="/analyze"
          className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
        >
          New Analysis
        </Link>
      </div>

      {analyses.length === 0 ? (
        <div className="text-center py-20 text-text-tertiary text-sm">
          No analyses yet.{" "}
          <Link href="/analyze" className="text-accent hover:text-accent-hover">
            Submit your first pitch
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {analyses.map((a) => {
            const scoreColor =
              a.overall_score !== null
                ? a.overall_score >= 70
                  ? "text-score-high"
                  : a.overall_score >= 40
                    ? "text-score-mid"
                    : "text-score-low"
                : "text-text-tertiary";

            return (
              <Link
                key={a.id}
                href={`/analyze/${a.id}`}
                className="block rounded border border-border bg-surface p-4 hover:border-accent/50 transition"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-text-primary">{a.company_name}</h3>
                    <p className="text-xs text-text-tertiary mt-0.5">
                      {a.created_at ? new Date(a.created_at).toLocaleDateString() : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    {a.overall_score !== null && (
                      <span className={`text-lg font-medium tabular-nums ${scoreColor}`}>
                        {Math.round(a.overall_score)}
                      </span>
                    )}
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[a.status] || "bg-zinc-100 text-zinc-600"}`}>
                      {STATUS_LABELS[a.status] || a.status}
                    </span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
