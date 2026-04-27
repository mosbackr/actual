"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ClaimBanner } from "./claim-banner";
import { PortfolioSection } from "./portfolio-section";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const DIMENSIONS = [
  "Portfolio Performance",
  "Deal Activity",
  "Exit Track Record",
  "Stage Expertise",
  "Sector Expertise",
  "Follow-on Rate",
  "Network Quality",
];

function scoreColor(score: number): string {
  if (score >= 80) return "#2D6A4F";
  if (score >= 60) return "#B8860B";
  if (score >= 40) return "#6B6B6B";
  return "#A23B3B";
}

interface RankingData {
  investor_id: string;
  firm_name: string;
  partner_name: string;
  overall_score: number;
  dimension_scores: Record<string, number>;
  narrative: string;
  scored_at: string;
}

function EditableField({
  value,
  onSave,
  className,
  tag: Tag = "h1",
}: {
  value: string;
  onSave: (v: string) => void;
  className?: string;
  tag?: "h1" | "p";
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  if (!editing) {
    return (
      <Tag
        className={`${className} cursor-pointer hover:opacity-70 transition`}
        onClick={() => { setDraft(value); setEditing(true); }}
        title="Click to edit"
      >
        {value}
      </Tag>
    );
  }

  return (
    <input
      autoFocus
      className={`${className} bg-transparent border-b border-accent outline-none text-center w-full`}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => { if (draft.trim() && draft !== value) onSave(draft.trim()); setEditing(false); }}
      onKeyDown={(e) => {
        if (e.key === "Enter") { if (draft.trim() && draft !== value) onSave(draft.trim()); setEditing(false); }
        if (e.key === "Escape") setEditing(false);
      }}
    />
  );
}

export default function ScoreDetailPage() {
  const { data: session, status } = useSession();
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [data, setData] = useState<RankingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showClaimBanner, setShowClaimBanner] = useState(false);
  const [claimDismissed, setClaimDismissed] = useState(false);
  const [isOwner, setIsOwner] = useState(false);
  const [rescoring, setRescoring] = useState(false);
  const [rescoreMsg, setRescoreMsg] = useState<string | null>(null);

  useEffect(() => {
    if (status === "loading") return;
    if (!session) {
      router.push(`/auth/signin?callbackUrl=/score/${id}`);
      return;
    }

    const token = (session as any)?.backendToken;
    if (!token) return;

    async function fetchRanking() {
      try {
        const res = await fetch(`${API_URL}/api/investors/${id}/ranking`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 403) {
          // User doesn't have access to this specific score — try their own
          const meRes = await fetch(`${API_URL}/api/investors/me/ranking`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (meRes.ok) {
            const meData = await meRes.json();
            router.replace(`/score/${meData.investor_id}`);
            return;
          }
          throw new Error("no_access");
        }
        if (!res.ok) throw new Error("Failed to load score data");
        const result = await res.json();
        setData(result);

        // Check if this investor profile can be claimed by current user
        const portfolioRes = await fetch(`${API_URL}/api/investors/${id}/portfolio`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (portfolioRes.ok) {
          const portfolioData = await portfolioRes.json();
          if (portfolioData.is_owner) {
            setIsOwner(true);
          } else {
            setShowClaimBanner(true);
          }
        }
      } catch (e: any) {
        setError(e.message || "An error occurred");
      } finally {
        setLoading(false);
      }
    }

    fetchRanking();
  }, [session, status, id, router]);

  if (status === "loading" || loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl py-16 px-6 text-center">
        <div
          style={{
            display: "inline-block",
            width: 48,
            height: 48,
            borderRadius: "50%",
            background: "#F28C28",
            color: "#fff",
            fontWeight: 700,
            fontSize: 24,
            lineHeight: "48px",
            textAlign: "center",
            marginBottom: 24,
          }}
        >
          D
        </div>
        <h1 className="font-serif text-3xl text-text-primary mb-3">
          Deep Thesis
        </h1>
        <p className="text-lg text-text-secondary mb-6">
          Data-driven investor intelligence, powered by founder feedback.
        </p>
        <div className="rounded border border-border bg-surface p-6 text-left mb-8">
          <h2 className="font-serif text-lg text-text-primary mb-4">
            What we do for investors
          </h2>
          <ul className="space-y-3 text-sm text-text-secondary">
            <li className="flex gap-3">
              <span style={{ color: "#F28C28", fontWeight: 600 }}>01</span>
              <span>
                <strong className="text-text-primary">Transparent Scoring</strong> — See how
                founders rate your deal activity, sector expertise, follow-on
                support, and more across 7 dimensions.
              </span>
            </li>
            <li className="flex gap-3">
              <span style={{ color: "#F28C28", fontWeight: 600 }}>02</span>
              <span>
                <strong className="text-text-primary">Benchmark Your Firm</strong> — Understand
                where you stand relative to peers and identify areas to
                strengthen your value proposition.
              </span>
            </li>
            <li className="flex gap-3">
              <span style={{ color: "#F28C28", fontWeight: 600 }}>03</span>
              <span>
                <strong className="text-text-primary">Actionable Insights</strong> — Each score
                comes with an analyst narrative explaining the data behind the
                numbers.
              </span>
            </li>
          </ul>
        </div>
        {session ? (
          <>
            <p className="text-sm text-text-tertiary mb-6">
              We don&apos;t have a score on file for your account yet. Check back soon.
            </p>
            <a
              href="/"
              className="inline-block px-6 py-3 rounded-full text-white font-semibold text-sm"
              style={{ background: "#F28C28" }}
            >
              Go to Dashboard
            </a>
          </>
        ) : (
          <>
            <p className="text-sm text-text-tertiary mb-6">
              Sign in to view your personalized investor score.
            </p>
            <a
              href={`/auth/signin?callbackUrl=/score/${id}`}
              className="inline-block px-6 py-3 rounded-full text-white font-semibold text-sm"
              style={{ background: "#F28C28" }}
            >
              Sign In to View Your Score
            </a>
          </>
        )}
      </div>
    );
  }

  if (!data) {
    return <div className="text-center py-20 text-text-tertiary">No score data found.</div>;
  }

  return (
    <div className="mx-auto max-w-4xl">
      {/* Header */}
      <div className="text-center mb-10">
        <p className="text-xs uppercase tracking-widest text-text-tertiary mb-2">
          Investor Score
        </p>
        {isOwner ? (
          <EditableField
            tag="h1"
            className="font-serif text-3xl text-text-primary mb-1"
            value={data.firm_name}
            onSave={async (v) => {
              const token = (session as any)?.backendToken;
              if (!token) return;
              await api.updateInvestorProfile(token, id, { firm_name: v });
              setData({ ...data, firm_name: v });
            }}
          />
        ) : (
          <h1 className="font-serif text-3xl text-text-primary mb-1">{data.firm_name}</h1>
        )}
        {isOwner ? (
          <EditableField
            tag="p"
            className="text-sm text-text-secondary mb-4"
            value={data.partner_name}
            onSave={async (v) => {
              const token = (session as any)?.backendToken;
              if (!token) return;
              await api.updateInvestorProfile(token, id, { partner_name: v });
              setData({ ...data, partner_name: v });
            }}
          />
        ) : (
          <p className="text-sm text-text-secondary mb-4">{data.partner_name}</p>
        )}
        <p
          className="text-6xl font-bold tabular-nums"
          style={{ color: scoreColor(data.overall_score) }}
        >
          {Math.round(data.overall_score)}
        </p>
      </div>

      {/* Claim Banner */}
      {showClaimBanner && !claimDismissed && (
        <ClaimBanner
          investorId={id}
          token={(session as any)?.backendToken}
          onClaimed={() => {
            setClaimDismissed(true);
            setShowClaimBanner(false);
          }}
        />
      )}

      {/* Portfolio */}
      <PortfolioSection
        investorId={id}
        token={(session as any)?.backendToken}
      />

      {/* Dimension Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
        {DIMENSIONS.map((dim) => {
          const key = dim.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
          const score = data.dimension_scores?.[key] ?? 0;
          const color = scoreColor(score);
          return (
            <div
              key={dim}
              className="rounded border border-border bg-surface p-4"
            >
              <p className="text-xs text-text-secondary mb-2">{dim}</p>
              <div className="flex items-baseline gap-1 mb-2">
                <span
                  className="text-2xl font-bold tabular-nums"
                  style={{ color }}
                >
                  {Math.round(score)}
                </span>
                <span className="text-xs text-text-tertiary">/ 100</span>
              </div>
              <div className="h-1.5 rounded-full bg-border overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(score, 100)}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Narrative */}
      {data.narrative && (
        <div className="rounded border border-border bg-surface p-6 mb-10">
          <h2 className="font-serif text-lg text-text-primary mb-3">
            Analyst Note
          </h2>
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
            {data.narrative}
          </p>
          <div className="flex items-center justify-between mt-4">
            {data.scored_at && (
              <p className="text-xs text-text-tertiary">
                Scored {new Date(data.scored_at).toLocaleDateString()}
              </p>
            )}
            {isOwner && (
              <button
                onClick={async () => {
                  const token = (session as any)?.backendToken;
                  if (!token) return;
                  setRescoring(true);
                  setRescoreMsg(null);
                  try {
                    await api.rescoreInvestor(token, id);
                    setRescoreMsg("Rescoring started — refresh in a minute to see updated scores.");
                  } catch {
                    setRescoreMsg("Failed to start rescore.");
                  }
                  setRescoring(false);
                }}
                disabled={rescoring}
                className="text-xs px-3 py-1.5 rounded border border-accent/30 text-accent hover:bg-accent/5 transition disabled:opacity-50"
              >
                {rescoring ? "Starting..." : "Re-evaluate Score"}
              </button>
            )}
          </div>
          {rescoreMsg && (
            <p className="text-xs text-accent mt-2">{rescoreMsg}</p>
          )}
        </div>
      )}

    </div>
  );
}
