"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";

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

export default function ScoreDetailPage() {
  const { data: session, status } = useSession();
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [data, setData] = useState<RankingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <h1 className="font-serif text-3xl text-text-primary mb-1">
          {data.firm_name}
        </h1>
        <p className="text-sm text-text-secondary mb-4">{data.partner_name}</p>
        <p
          className="text-6xl font-bold tabular-nums"
          style={{ color: scoreColor(data.overall_score) }}
        >
          {Math.round(data.overall_score)}
        </p>
      </div>

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
          {data.scored_at && (
            <p className="text-xs text-text-tertiary mt-4">
              Scored {new Date(data.scored_at).toLocaleDateString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
