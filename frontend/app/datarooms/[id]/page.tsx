"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DataroomDetail, DataroomSectionReview } from "@/lib/api";

/* ── Section label mapping ─────────────────────────────────────────── */

const SECTION_LABELS: Record<string, string> = {
  corporate: "Corporate Documents",
  financials: "Financials",
  fundraising: "Fundraising",
  product: "Product",
  legal: "Legal",
  team: "Team",
  custom: "Custom Criteria",
};

/* ── ScoreBadge ────────────────────────────────────────────────────── */

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium text-text-tertiary bg-surface-alt">
        &mdash;
      </span>
    );
  }

  let colors: string;
  if (score >= 70) {
    colors = "text-green-700 bg-green-50";
  } else if (score >= 40) {
    colors = "text-yellow-700 bg-yellow-50";
  } else {
    colors = "text-red-700 bg-red-50";
  }

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors}`}>
      {score}
    </span>
  );
}

/* ── SectionReviewCard ─────────────────────────────────────────────── */

function SectionReviewCard({ review }: { review: DataroomSectionReview }) {
  const [expanded, setExpanded] = useState(false);

  const label =
    review.section === "custom" && review.criteria_description
      ? review.criteria_description
      : SECTION_LABELS[review.section] || review.section;

  return (
    <div className="rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={() => setExpanded((p) => !p)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-text-primary">{label}</span>
          <ScoreBadge score={review.score} />
        </div>
        <svg
          className={`h-4 w-4 text-text-tertiary transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-border px-5 py-4">
          {review.status === "pending" && (
            <p className="text-sm text-blue-600 animate-pulse">Analyzing...</p>
          )}

          {review.status === "failed" && (
            <p className="text-sm text-red-600">Review failed</p>
          )}

          {review.status === "complete" && (
            <div className="space-y-4">
              {review.summary && (
                <p className="text-sm text-text-secondary whitespace-pre-line">{review.summary}</p>
              )}

              {review.findings && (
                <div className="space-y-3">
                  {/* Strengths */}
                  {review.findings.strengths && review.findings.strengths.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-green-700 mb-1">Strengths</p>
                      <ul className="space-y-1">
                        {review.findings.strengths.map((s, i) => (
                          <li key={i} className="text-sm text-green-700 flex gap-1.5">
                            <span className="shrink-0">+</span>
                            <span>{s}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Concerns */}
                  {review.findings.concerns && review.findings.concerns.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-orange-600 mb-1">Concerns</p>
                      <ul className="space-y-1">
                        {review.findings.concerns.map((c, i) => (
                          <li key={i} className="text-sm text-orange-600 flex gap-1.5">
                            <span className="shrink-0">!</span>
                            <span>{c}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Missing */}
                  {review.findings.missing && review.findings.missing.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-red-600 mb-1">Missing</p>
                      <ul className="space-y-1">
                        {review.findings.missing.map((m, i) => (
                          <li key={i} className="text-sm text-red-600 flex gap-1.5">
                            <span className="shrink-0">-</span>
                            <span>{m}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Recommendation */}
                  {review.findings.recommendation && (
                    <div className="rounded bg-surface-alt px-3 py-2">
                      <p className="text-xs font-medium text-text-primary mb-0.5">Recommendation</p>
                      <p className="text-sm text-text-secondary">{review.findings.recommendation}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Helpers ────────────────────────────────────────────────────────── */

function formatBytes(bytes: number): string {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

/* ── Main Page ─────────────────────────────────────────────────────── */

export default function DataroomDetailPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const dataroomId = params.id as string;
  const router = useRouter();

  const [dataroom, setDataroom] = useState<DataroomDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [activeTab, setActiveTab] = useState<"reviews" | "analysis">("reviews");

  const loadDataroom = useCallback(async () => {
    if (!token || !dataroomId) return;
    try {
      const data = await api.getDataroom(token, dataroomId);
      setDataroom(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, dataroomId]);

  useEffect(() => {
    loadDataroom();
  }, [loadDataroom]);

  // Poll when status is analyzing
  useEffect(() => {
    if (!token || !dataroom || dataroom.status !== "analyzing") return;
    const interval = setInterval(async () => {
      try {
        const data = await api.getDataroom(token, dataroomId);
        setDataroom(data);
        if (data.status !== "analyzing") {
          clearInterval(interval);
        }
      } catch {
        // silent
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [token, dataroom?.status, dataroomId]);

  const handleDelete = async () => {
    if (!token || !dataroomId) return;
    if (!confirm("Delete this dataroom request? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.deleteDataroom(token, dataroomId);
      router.push("/datarooms");
    } catch (e: any) {
      setError(e.message);
      setDeleting(false);
    }
  };

  /* ── Loading skeleton ────────────────────────────────────────────── */

  if (!session) {
    return <div className="p-8 text-text-secondary">Sign in to access Datarooms.</div>;
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10 space-y-4 animate-pulse">
        <div className="h-4 w-24 rounded bg-surface-alt" />
        <div className="h-8 w-64 rounded bg-surface-alt" />
        <div className="h-4 w-48 rounded bg-surface-alt" />
        <div className="h-px bg-border my-6" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-lg bg-surface-alt" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !dataroom) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <p className="text-red-600">{error || "Dataroom not found"}</p>
        <Link href="/datarooms" className="mt-4 inline-block text-sm text-accent hover:underline">
          Back to Datarooms
        </Link>
      </div>
    );
  }

  /* ── Derived data ────────────────────────────────────────────────── */

  const title = dataroom.company_name || dataroom.founder_email;

  const standardReviews = dataroom.section_reviews.filter((r) => r.section !== "custom");
  const customReviews = dataroom.section_reviews.filter((r) => r.section === "custom");

  // Group documents by section
  const docsBySection: Record<string, typeof dataroom.documents> = {};
  for (const doc of dataroom.documents) {
    if (!docsBySection[doc.section]) docsBySection[doc.section] = [];
    docsBySection[doc.section].push(doc);
  }

  /* ── Render ──────────────────────────────────────────────────────── */

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      {/* Back link */}
      <Link href="/datarooms" className="text-sm text-accent hover:underline mb-4 inline-block">
        &larr; Back to Datarooms
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <h1 className="text-2xl font-serif text-text-primary">{title}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {dataroom.founder_name && <span>{dataroom.founder_name} &middot; </span>}
            {dataroom.founder_email}
            <span className="mx-1">&middot;</span>
            {new Date(dataroom.created_at).toLocaleDateString()}
          </p>
        </div>

        {dataroom.status !== "analyzing" && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="rounded border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition"
          >
            {deleting ? "Deleting..." : "Delete"}
          </button>
        )}
      </div>

      {/* Status banners */}
      {dataroom.status === "analyzing" && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 mb-6">
          <p className="text-sm font-medium text-orange-700 animate-pulse">
            Analysis is running... This page will update automatically.
          </p>
        </div>
      )}

      {dataroom.status === "pending" && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 mb-6">
          <p className="text-sm font-medium text-yellow-700">
            Waiting for founder to accept the invitation and upload documents.
          </p>
        </div>
      )}

      {dataroom.status === "uploading" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 mb-6">
          <p className="text-sm font-medium text-blue-700">
            Founder is uploading documents... ({dataroom.documents.length} file{dataroom.documents.length !== 1 ? "s" : ""} so far)
          </p>
        </div>
      )}

      {/* Tab bar (only for complete status) */}
      {dataroom.status === "complete" && (
        <div className="flex gap-1 border-b border-border mb-6 mt-4">
          {(["reviews", "analysis"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
                activeTab === tab
                  ? "border-accent text-accent"
                  : "border-transparent text-text-tertiary hover:text-text-secondary"
              }`}
            >
              {tab === "reviews" ? "Section Reviews" : "Pitch Analysis"}
            </button>
          ))}
        </div>
      )}

      {/* Reviews tab */}
      {(dataroom.status !== "complete" || activeTab === "reviews") && dataroom.section_reviews.length > 0 && (
        <div className="mb-8">
          {dataroom.status !== "complete" && (
            <h2 className="text-lg font-medium text-text-primary mb-4">Section Reviews</h2>
          )}

          {/* Standard section reviews */}
          {standardReviews.length > 0 && (
            <div className="space-y-3 mb-4">
              {standardReviews.map((review) => (
                <SectionReviewCard key={review.id} review={review} />
              ))}
            </div>
          )}

          {/* Custom criteria reviews */}
          {customReviews.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wide mt-4 mb-2">
                Custom Criteria
              </h3>
              {customReviews.map((review) => (
                <SectionReviewCard key={review.id} review={review} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Analysis tab */}
      {dataroom.status === "complete" && activeTab === "analysis" && (
        <div className="mb-8">
          {dataroom.analysis_id ? (
            <div className="rounded-lg border border-border bg-surface p-6 text-center">
              <p className="text-sm text-text-secondary mb-4">
                View the full pitch analysis generated from the dataroom documents.
              </p>
              <Link
                href={`/analyze/${dataroom.analysis_id}`}
                className="inline-block rounded bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent/90 transition"
              >
                View Pitch Analysis
              </Link>
            </div>
          ) : (
            <p className="text-sm text-text-tertiary">No pitch analysis available for this dataroom.</p>
          )}
        </div>
      )}

      {/* Documents section */}
      {dataroom.documents.length > 0 && (
        <div>
          <h2 className="text-lg font-medium text-text-primary mb-4">Documents</h2>
          <div className="space-y-4">
            {Object.entries(docsBySection).map(([section, docs]) => (
              <div key={section}>
                <h3 className="text-sm font-medium text-text-tertiary mb-2">
                  {SECTION_LABELS[section] || section}
                </h3>
                <div className="space-y-1">
                  {docs.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between rounded border border-border bg-surface px-4 py-2.5"
                    >
                      <span className="text-sm text-text-primary truncate">{doc.original_filename}</span>
                      <span className="text-xs text-text-tertiary shrink-0 ml-3">
                        {formatBytes(doc.file_size_bytes)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
