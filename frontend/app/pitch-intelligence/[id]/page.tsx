"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type {
  PitchSessionDetail,
  PitchTranscript,
  PitchPhaseResult,
} from "@/lib/types";

export default function PitchSessionPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <PitchSessionContent />
    </Suspense>
  );
}

function PitchSessionContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const sessionId = params.id as string;
  const router = useRouter();

  const [ps, setPs] = useState<PitchSessionDetail | null>(null);
  const [transcript, setTranscript] = useState<PitchTranscript | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"transcript" | "fact-check" | "analysis" | "scores">("transcript");
  const [factCheckTab, setFactCheckTab] = useState<"founders" | "investors">("founders");

  // Speaker labeling state
  const [speakerLabels, setSpeakerLabels] = useState<Record<string, { name: string; role: string }>>({});
  const [labeling, setLabeling] = useState(false);

  const loadSession = useCallback(async () => {
    if (!token || !sessionId) return;
    try {
      const data = await api.getPitchSession(token, sessionId);
      setPs(data);

      // Load transcript if available
      if (["labeling", "analyzing", "complete"].includes(data.status)) {
        try {
          const t = await api.getPitchTranscript(token, sessionId);
          setTranscript(t);
          // Initialize speaker labels
          if (data.status === "labeling" && t.speakers) {
            const labels: Record<string, { name: string; role: string }> = {};
            t.speakers.forEach((sp) => {
              labels[sp.id] = { name: sp.name || sp.label || "", role: "founder" };
            });
            setSpeakerLabels(labels);
          }
        } catch {
          // transcript not ready yet
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  // Poll for status updates when transcribing or analyzing
  useEffect(() => {
    if (!token || !ps || !["transcribing", "analyzing"].includes(ps.status)) return;
    const interval = setInterval(async () => {
      try {
        const data = await api.getPitchSession(token, sessionId);
        setPs(data);
        if (["labeling", "complete", "failed"].includes(data.status)) {
          clearInterval(interval);
          if (data.status === "labeling") {
            const t = await api.getPitchTranscript(token, sessionId);
            setTranscript(t);
            const labels: Record<string, { name: string; role: string }> = {};
            t.speakers?.forEach((sp) => {
              labels[sp.id] = { name: sp.name || sp.label || "", role: "founder" };
            });
            setSpeakerLabels(labels);
          }
        }
      } catch {
        // silent
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [token, ps?.status, sessionId]);

  const handleLabelSubmit = async () => {
    if (!token) return;
    setLabeling(true);
    try {
      const speakers = Object.entries(speakerLabels).map(([id, info]) => ({
        speaker_id: id,
        name: info.name || `Speaker ${parseInt(id) + 1}`,
        role: info.role,
      }));
      await api.labelPitchSpeakers(token, sessionId, speakers);
      await loadSession();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLabeling(false);
    }
  };

  const getPhaseResult = (phase: string): PitchPhaseResult | undefined => {
    return ps?.results?.find((r) => r.phase === phase);
  };

  const phaseStatus = (phase: string) => {
    const r = getPhaseResult(phase);
    if (!r) return "pending";
    return r.status;
  };

  if (!session) {
    return <div className="p-8 text-text-secondary">Sign in to access Pitch Intelligence.</div>;
  }
  if (loading) {
    return <div className="p-8 text-text-secondary">Loading...</div>;
  }
  if (error || !ps) {
    return <div className="p-8 text-red-600">{error || "Session not found"}</div>;
  }

  // ── Transcribing state ─────────────────────────────────────────────
  if (ps.status === "uploading" || ps.status === "transcribing") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <div className="animate-pulse text-4xl mb-4">&#127908;</div>
        <h2 className="text-xl font-medium text-text-primary mb-2">
          {ps.status === "uploading" ? "Processing upload..." : "Transcribing your pitch..."}
        </h2>
        <p className="text-text-secondary">
          This usually takes 1-3 minutes depending on the recording length.
        </p>
      </div>
    );
  }

  // ── Speaker labeling state ─────────────────────────────────────────
  if (ps.status === "labeling") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="text-2xl font-serif text-text-primary mb-2">Label Speakers</h1>
        <p className="text-text-secondary mb-6">
          We detected {transcript?.speakers?.length || 0} speakers. Assign names and roles to each.
        </p>

        <div className="space-y-4 mb-8">
          {transcript?.speakers?.map((sp) => {
            const label = speakerLabels[sp.id] || { name: "", role: "founder" };
            // Find sample segments for this speaker
            const samples = (transcript.segments || [])
              .filter((seg) => seg.speaker === sp.id || seg.speaker_id === sp.id)
              .slice(0, 2);
            return (
              <div key={sp.id} className="rounded-lg border border-border bg-surface p-4">
                <p className="text-sm text-text-tertiary mb-2">{sp.label || `Speaker ${parseInt(sp.id) + 1}`}</p>
                {samples.length > 0 && (
                  <div className="mb-3 space-y-1">
                    {samples.map((seg, i) => (
                      <p key={i} className="text-sm text-text-secondary italic">
                        &ldquo;{seg.text.slice(0, 150)}{seg.text.length > 150 ? "..." : ""}&rdquo;
                      </p>
                    ))}
                  </div>
                )}
                <div className="flex gap-3">
                  <input
                    type="text"
                    placeholder="Name"
                    value={label.name}
                    onChange={(e) =>
                      setSpeakerLabels((prev) => ({
                        ...prev,
                        [sp.id]: { ...prev[sp.id], name: e.target.value },
                      }))
                    }
                    className="flex-1 rounded border border-border bg-background px-3 py-1.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
                  />
                  <select
                    value={label.role}
                    onChange={(e) =>
                      setSpeakerLabels((prev) => ({
                        ...prev,
                        [sp.id]: { ...prev[sp.id], role: e.target.value },
                      }))
                    }
                    className="rounded border border-border bg-background px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
                  >
                    <option value="founder">Founder</option>
                    <option value="investor">Investor</option>
                    <option value="other">Other</option>
                  </select>
                </div>
              </div>
            );
          })}
        </div>

        <button
          onClick={handleLabelSubmit}
          disabled={labeling}
          className="rounded bg-accent px-6 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50 transition"
        >
          {labeling ? "Starting Analysis..." : "Start Analysis"}
        </button>
      </div>
    );
  }

  // ── Failed state ───────────────────────────────────────────────────
  if (ps.status === "failed") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <h2 className="text-xl font-medium text-red-600 mb-2">Analysis Failed</h2>
        <p className="text-text-secondary">{ps.error || "An error occurred during analysis."}</p>
        <button
          onClick={() => router.push("/pitch-intelligence")}
          className="mt-4 text-sm text-accent hover:underline"
        >
          Back to Pitch Intelligence
        </button>
      </div>
    );
  }

  // ── Analyzing / Complete — show results ────────────────────────────

  const claimResult = getPhaseResult("claim_extraction");
  const founderFcResult = getPhaseResult("fact_check_founders");
  const investorFcResult = getPhaseResult("fact_check_investors");
  const conversationResult = getPhaseResult("conversation_analysis");
  const scoringResult = getPhaseResult("scoring");
  const benchmarkResult = getPhaseResult("benchmark");

  const scores = ps.scores || (scoringResult?.result?.scores as Record<string, number>) || {};
  const recommendations = (scoringResult?.result?.recommendations || []) as any[];
  const executiveSummary = (scoringResult?.result?.executive_summary as string) || "";

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-serif text-text-primary">
            {ps.title || "Untitled Pitch"}
          </h1>
          <p className="text-sm text-text-tertiary mt-1">
            {ps.created_at ? new Date(ps.created_at).toLocaleDateString() : ""}
            {ps.file_duration_seconds ? ` · ${Math.round(ps.file_duration_seconds / 60)} min` : ""}
          </p>
        </div>
        {scores.overall != null && (
          <div className="text-right">
            <div className="text-3xl font-bold text-accent">{scores.overall}</div>
            <div className="text-xs text-text-tertiary">Overall Score</div>
          </div>
        )}
      </div>

      {/* Phase Progress */}
      {ps.status === "analyzing" && (
        <div className="mb-6 rounded-lg border border-border bg-surface p-4">
          <p className="text-sm font-medium text-text-primary mb-3">Analysis in progress...</p>
          <div className="grid grid-cols-6 gap-2">
            {["claim_extraction", "fact_check_founders", "fact_check_investors", "conversation_analysis", "scoring", "benchmark"].map((phase) => {
              const st = phaseStatus(phase);
              const label = phase.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
              return (
                <div key={phase} className="text-center">
                  <div
                    className={`h-2 rounded-full mb-1 ${
                      st === "complete" ? "bg-green-500" :
                      st === "running" ? "bg-blue-500 animate-pulse" :
                      st === "failed" ? "bg-red-500" :
                      "bg-surface-alt"
                    }`}
                  />
                  <p className="text-[10px] text-text-tertiary leading-tight">{label}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Executive Summary */}
      {executiveSummary && (
        <div className="mb-6 rounded-lg border border-border bg-surface p-5">
          <h3 className="text-sm font-medium text-text-primary mb-2">Executive Summary</h3>
          <p className="text-sm text-text-secondary whitespace-pre-line">{executiveSummary}</p>
        </div>
      )}

      {/* Valuation Assessment */}
      {(scoringResult?.result as any)?.valuation_assessment && (
        <div className="mb-6 rounded-lg border border-accent/30 bg-accent/5 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-text-primary">Valuation Assessment</h3>
            {(scoringResult?.result as any)?.valuation_assessment?.estimated_valuation && (
              <span className="text-lg font-medium text-accent">
                {(scoringResult?.result as any).valuation_assessment.estimated_valuation}
              </span>
            )}
          </div>
          {(scoringResult?.result as any)?.valuation_assessment?.justification && (
            <p className="text-sm text-text-secondary whitespace-pre-line">
              {(scoringResult?.result as any).valuation_assessment.justification}
            </p>
          )}
          {(scoringResult?.result as any)?.valuation_assessment?.founders_ask_reasonable != null && (
            <p className="text-xs mt-2 font-medium">
              Founders&apos; ask:{" "}
              <span className={(scoringResult?.result as any).valuation_assessment.founders_ask_reasonable ? "text-green-600" : "text-red-600"}>
                {(scoringResult?.result as any).valuation_assessment.founders_ask_reasonable ? "Reasonable" : "Needs adjustment"}
              </span>
            </p>
          )}
        </div>
      )}

      {/* Technical Expert Review */}
      {(scoringResult?.result as any)?.technical_expert_review && (
        <div className="mb-6 rounded-lg border border-border bg-surface p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-text-primary">Technical Expert Review</h3>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                (scoringResult?.result as any).technical_expert_review.technical_feasibility === "Proven" ? "bg-green-100 text-green-700" :
                (scoringResult?.result as any).technical_expert_review.technical_feasibility === "Plausible" ? "bg-blue-100 text-blue-700" :
                (scoringResult?.result as any).technical_expert_review.technical_feasibility === "Speculative" ? "bg-yellow-100 text-yellow-700" :
                "bg-red-100 text-red-700"
              }`}>
                {(scoringResult?.result as any).technical_expert_review.technical_feasibility}
              </span>
              <span className="text-xs text-text-tertiary">
                TRL {(scoringResult?.result as any).technical_expert_review.trl_level}/9
              </span>
            </div>
          </div>
          <p className="text-sm text-text-secondary whitespace-pre-line mb-3">
            {(scoringResult?.result as any).technical_expert_review.scientific_consensus}
          </p>
          {(scoringResult?.result as any).technical_expert_review.red_flags?.length > 0 && (
            <div className="mb-3">
              <p className="text-xs font-medium text-red-600 mb-1">Red Flags</p>
              <ul className="space-y-1">
                {(scoringResult?.result as any).technical_expert_review.red_flags.map((flag: string, i: number) => (
                  <li key={i} className="text-xs text-red-600 flex gap-1.5">
                    <span>&#9888;</span> {flag}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-sm text-text-secondary italic">
            {(scoringResult?.result as any).technical_expert_review.verdict}
          </p>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-border mb-6">
        {(["transcript", "fact-check", "analysis", "scores"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              activeTab === tab
                ? "border-accent text-accent"
                : "border-transparent text-text-tertiary hover:text-text-secondary"
            }`}
          >
            {tab === "fact-check" ? "Fact-Check" : tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "transcript" && (
        <TranscriptPanel sessionId={sessionId} token={token} transcript={transcript} />
      )}

      {activeTab === "fact-check" && (
        <div>
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setFactCheckTab("founders")}
              className={`px-3 py-1 text-sm rounded ${factCheckTab === "founders" ? "bg-accent text-white" : "bg-surface-alt text-text-secondary"}`}
            >
              Founder Claims
            </button>
            <button
              onClick={() => setFactCheckTab("investors")}
              className={`px-3 py-1 text-sm rounded ${factCheckTab === "investors" ? "bg-accent text-white" : "bg-surface-alt text-text-secondary"}`}
            >
              Investor Advice
            </button>
          </div>
          <FactCheckPanel
            result={factCheckTab === "founders" ? founderFcResult : investorFcResult}
          />
        </div>
      )}

      {activeTab === "analysis" && (
        <ConversationAnalysisPanel result={conversationResult} />
      )}

      {activeTab === "scores" && (
        <ScoresPanel
          scores={scores}
          percentiles={ps.benchmark_percentiles || {}}
          recommendations={recommendations}
        />
      )}
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────

function TranscriptPanel({
  sessionId,
  token,
  transcript,
}: {
  sessionId: string;
  token: string;
  transcript: PitchTranscript | null;
}) {
  const [data, setData] = useState<PitchTranscript | null>(transcript);

  useEffect(() => {
    if (transcript) {
      setData(transcript);
      return;
    }
    if (!token || !sessionId) return;
    api.getPitchTranscript(token, sessionId).then(setData).catch(() => {});
  }, [token, sessionId, transcript]);

  if (!data) return <p className="text-text-tertiary text-sm">Transcript not available yet.</p>;

  const roleColors: Record<string, string> = {
    founder: "text-blue-600",
    investor: "text-emerald-600",
    other: "text-text-secondary",
  };

  return (
    <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
      {data.segments?.map((seg, i) => {
        const role = seg.speaker_role || "other";
        const name = seg.speaker_name || seg.speaker || `Speaker ${i}`;
        const time = formatTime(seg.start);
        return (
          <div key={i} className="flex gap-3">
            <span className="text-xs text-text-tertiary w-12 shrink-0 pt-0.5">{time}</span>
            <div>
              <span className={`text-sm font-medium ${roleColors[role] || roleColors.other}`}>
                {name}
              </span>
              <p className="text-sm text-text-primary">{seg.text}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FactCheckPanel({ result }: { result?: PitchPhaseResult }) {
  if (!result || result.status === "pending") {
    return <p className="text-text-tertiary text-sm">Waiting for fact-check to start...</p>;
  }
  if (result.status === "running") {
    return <p className="text-blue-600 text-sm animate-pulse">Fact-checking in progress...</p>;
  }
  if (result.status === "failed") {
    return <p className="text-red-600 text-sm">Fact-check failed: {result.error}</p>;
  }

  const data = result.result as any;
  const claims = data?.checked_claims || [];

  const verdictBadge = (verdict: string) => {
    const styles: Record<string, string> = {
      verified: "bg-green-100 text-green-700",
      disputed: "bg-red-100 text-red-700",
      unverifiable: "bg-yellow-100 text-yellow-700",
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[verdict] || styles.unverifiable}`}>
        {verdict}
      </span>
    );
  };

  return (
    <div>
      {data?.summary && (
        <p className="text-sm text-text-secondary mb-4">{data.summary}</p>
      )}
      <div className="space-y-3">
        {claims.map((claim: any, i: number) => (
          <div key={i} className="rounded border border-border bg-surface p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
              <p className="text-sm text-text-primary italic">
                &ldquo;{claim.original_claim?.quote || claim.quote || "—"}&rdquo;
              </p>
              {verdictBadge(claim.verdict)}
            </div>
            <p className="text-sm text-text-secondary">{claim.explanation}</p>
            {claim.sources && (
              <p className="text-xs text-text-tertiary mt-1">Sources: {claim.sources}</p>
            )}
          </div>
        ))}
        {claims.length === 0 && (
          <p className="text-text-tertiary text-sm">No claims found for this category.</p>
        )}
      </div>
    </div>
  );
}

function ConversationAnalysisPanel({ result }: { result?: PitchPhaseResult }) {
  if (!result || result.status === "pending") {
    return <p className="text-text-tertiary text-sm">Waiting for conversation analysis...</p>;
  }
  if (result.status === "running") {
    return <p className="text-blue-600 text-sm animate-pulse">Analyzing conversation...</p>;
  }
  if (result.status === "failed") {
    return <p className="text-red-600 text-sm">Analysis failed: {result.error}</p>;
  }

  const data = result.result as any;

  const renderSection = (title: string, section: any) => {
    if (!section) return null;
    return (
      <div className="rounded-lg border border-border bg-surface p-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-text-primary">{title}</h4>
          {section.score != null && (
            <span className="text-lg font-medium text-accent">{section.score}</span>
          )}
        </div>
        <p className="text-sm text-text-secondary mb-3">{section.assessment}</p>
        {section.highlights && (
          <div className="space-y-1">
            {section.highlights.map((h: any, i: number) => (
              <p key={i} className="text-xs text-text-tertiary">
                <span className="font-mono">[{h.timestamp}]</span> {h.observation}
              </p>
            ))}
          </div>
        )}
        {section.tension_points && section.tension_points.length > 0 && (
          <div className="mt-3 space-y-1">
            <p className="text-xs font-medium text-red-600">Tension Points:</p>
            {section.tension_points.map((t: any, i: number) => (
              <p key={i} className="text-xs text-text-tertiary">
                <span className="font-mono">[{t.timestamp}]</span> {t.description}
              </p>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      {renderSection("Presentation Quality", data?.presentation_quality)}
      {renderSection("Meeting Dynamics", data?.meeting_dynamics)}
      {renderSection("Strategic Read", data?.strategic_read)}
      {data?.environment_summary && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <h4 className="text-sm font-medium text-text-primary mb-2">Pitch Environment</h4>
          <p className="text-sm text-text-secondary">{data.environment_summary}</p>
        </div>
      )}
    </div>
  );
}

function ScoresPanel({
  scores,
  percentiles,
  recommendations,
}: {
  scores: Record<string, number>;
  percentiles: Record<string, number>;
  recommendations: any[];
}) {
  const dimensions = [
    { key: "pitch_clarity", label: "Pitch Clarity" },
    { key: "financial_rigor", label: "Financial Rigor" },
    { key: "q_and_a_handling", label: "Q&A Handling" },
    { key: "investor_engagement", label: "Investor Engagement" },
    { key: "fact_accuracy", label: "Fact Accuracy" },
  ];

  if (Object.keys(scores).length === 0) {
    return <p className="text-text-tertiary text-sm">Scores not available yet.</p>;
  }

  return (
    <div>
      {/* Score bars */}
      <div className="rounded-lg border border-border bg-surface p-5 mb-6">
        <h4 className="text-sm font-medium text-text-primary mb-4">Dimension Scores</h4>
        <div className="space-y-3">
          {dimensions.map(({ key, label }) => {
            const score = scores[key];
            const pct = percentiles[key];
            if (score == null) return null;
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-text-secondary">{label}</span>
                  <span className="font-medium text-text-primary">{score}/100</span>
                </div>
                <div className="h-2 rounded-full bg-surface-alt overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent transition-all"
                    style={{ width: `${score}%` }}
                  />
                </div>
                {pct != null && (
                  <p className="text-[10px] text-text-tertiary mt-0.5">{pct}th percentile</p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <h4 className="text-sm font-medium text-text-primary mb-4">Recommendations</h4>
          <div className="space-y-4">
            {recommendations.map((rec: any, i: number) => (
              <div key={i} className="flex gap-3">
                <span
                  className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                    rec.impact === "high"
                      ? "bg-red-100 text-red-700"
                      : rec.impact === "medium"
                      ? "bg-yellow-100 text-yellow-700"
                      : "bg-green-100 text-green-700"
                  }`}
                >
                  {i + 1}
                </span>
                <div>
                  <p className="text-sm font-medium text-text-primary">{rec.title}</p>
                  <p className="text-sm text-text-secondary">{rec.description}</p>
                  {rec.transcript_reference && (
                    <p className="text-xs text-text-tertiary mt-0.5 font-mono">
                      {rec.transcript_reference}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
