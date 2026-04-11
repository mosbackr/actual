"use client";

import { useEffect, useState, useCallback, useRef, use } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StartupEditor } from "@/components/StartupEditor";
import { DimensionManager } from "@/components/DimensionManager";
import { ExpertPicker } from "@/components/ExpertPicker";
import { adminApi } from "@/lib/api";
import type { StartupFullDetail, DDTemplate, Dimension, ApprovedExpert, Assignment } from "@/lib/types";

function ScoreBar({ score, label }: { score: number; label: string }) {
  const color = score >= 70 ? "bg-score-high" : score >= 40 ? "bg-score-mid" : "bg-score-low";
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-text-tertiary w-40 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-hover-row rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs font-medium text-text-primary w-8 text-right">{score}</span>
    </div>
  );
}

function EnrichmentBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    none: { label: "Not Enriched", cls: "bg-hover-row text-text-tertiary" },
    running: { label: "Enriching...", cls: "bg-accent/10 text-accent animate-pulse" },
    complete: { label: "Enriched", cls: "bg-score-high/10 text-score-high" },
    failed: { label: "Enrichment Failed", cls: "bg-score-low/10 text-score-low" },
  };
  const { label, cls } = map[status] || map.none;
  return <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${cls}`}>{label}</span>;
}

export default function StartupDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const [startup, setStartup] = useState<StartupFullDetail | null>(null);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [templates, setTemplates] = useState<DDTemplate[]>([]);
  const [experts, setExperts] = useState<ApprovedExpert[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchingLogo, setFetchingLogo] = useState(false);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [enriching, setEnriching] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async () => {
    if (!session?.backendToken) return;
    setLoading(true);
    try {
      const [detail, dims, tmpls, exps, assigns] = await Promise.all([
        adminApi.getStartupFullDetail(session.backendToken, id),
        adminApi.getDimensions(session.backendToken, id),
        adminApi.getTemplates(session.backendToken),
        adminApi.getApprovedExperts(session.backendToken),
        adminApi.getAssignments(session.backendToken, id),
      ]);
      setStartup(detail);
      setDimensions(dims);
      setTemplates(tmpls);
      setExperts(exps);
      setAssignments(assigns);
    } finally {
      setLoading(false);
    }
  }, [session?.backendToken, id]);

  // Initial load
  useEffect(() => {
    if (session?.backendToken) loadAll();
  }, [session?.backendToken, loadAll]);

  // Poll enrichment status while running
  useEffect(() => {
    if (startup?.enrichment_status === "running" && session?.backendToken) {
      pollRef.current = setInterval(async () => {
        try {
          const statusResp = await adminApi.getEnrichmentStatus(session.backendToken!, id);
          if (statusResp.enrichment_status !== "running") {
            // Enrichment finished — reload everything
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setEnriching(false);
            await loadAll();
          }
        } catch {
          // ignore poll errors
        }
      }, 3000);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [startup?.enrichment_status, session?.backendToken, id, loadAll]);

  async function handleTriggerEnrichment() {
    if (!session?.backendToken) return;
    setEnriching(true);
    try {
      await adminApi.triggerEnrichment(session.backendToken, id);
      // Reload to pick up "running" status
      await loadAll();
    } catch {
      setEnriching(false);
    }
  }

  async function handleFetchLogo() {
    if (!session?.backendToken) return;
    setFetchingLogo(true);
    setLogoError(null);
    try {
      await adminApi.fetchLogo(session.backendToken, id);
      await loadAll();
    } catch (err) {
      setLogoError(err instanceof Error ? err.message : "Failed to fetch logo");
    } finally {
      setFetchingLogo(false);
    }
  }

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading || !startup ? (
          <p className="text-text-tertiary">Loading...</p>
        ) : (
          <div className="space-y-8">
            {/* 1. Header */}
            <div className="flex items-center gap-4">
              {startup.logo_url ? (
                <img
                  src={startup.logo_url}
                  alt={startup.name}
                  className="w-12 h-12 rounded border border-border object-contain bg-white"
                />
              ) : (
                <div className="w-12 h-12 rounded border border-border bg-hover-row flex items-center justify-center text-text-tertiary text-lg font-serif">
                  {startup.name.charAt(0)}
                </div>
              )}
              <div>
                <h2 className="font-serif text-xl text-text-primary">{startup.name}</h2>
                {startup.tagline && (
                  <p className="text-sm text-text-secondary">{startup.tagline}</p>
                )}
                {startup.website_url && (
                  <a
                    href={startup.website_url.startsWith("http") ? startup.website_url : `https://${startup.website_url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-text-tertiary hover:text-accent transition"
                  >
                    {startup.website_url}
                  </a>
                )}
              </div>
              <div className="ml-auto flex items-center gap-3">
                <EnrichmentBadge status={startup.enrichment_status} />
                {startup.website_url && (
                  <button
                    onClick={handleFetchLogo}
                    disabled={fetchingLogo}
                    className="px-3 py-1.5 text-sm border border-border rounded text-text-secondary hover:text-accent hover:border-accent disabled:opacity-40 transition"
                  >
                    {fetchingLogo ? "Fetching..." : startup.logo_url ? "Refresh Logo" : "Fetch Logo"}
                  </button>
                )}
                <button
                  onClick={handleTriggerEnrichment}
                  disabled={enriching || startup.enrichment_status === "running"}
                  className="px-3 py-1.5 text-sm border border-accent rounded text-accent hover:bg-accent hover:text-white disabled:opacity-40 transition"
                >
                  {startup.enrichment_status === "running" || enriching
                    ? "Enriching..."
                    : startup.enrichment_status === "complete"
                      ? "Re-run Enrichment"
                      : "Enrich Startup"}
                </button>
              </div>
            </div>
            {logoError && (
              <p className="text-sm text-score-low">{logoError}</p>
            )}

            {/* 2. Enrichment error */}
            {startup.enrichment_status === "failed" && startup.enrichment_error && (
              <div className="rounded border border-score-low/30 bg-score-low/5 p-4">
                <p className="text-sm text-score-low font-medium">Enrichment Failed</p>
                <p className="text-sm text-text-secondary mt-1">{startup.enrichment_error}</p>
              </div>
            )}

            {/* 3. AI Investment Memo */}
            {startup.ai_review && (
              <section className="rounded border border-border bg-surface p-6 space-y-5">
                <div className="flex items-center justify-between">
                  <h3 className="font-serif text-lg text-text-primary">AI Investment Memo</h3>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-text-tertiary">Overall Score</span>
                    <span
                      className={`text-2xl font-bold ${
                        startup.ai_review.overall_score >= 70
                          ? "text-score-high"
                          : startup.ai_review.overall_score >= 40
                            ? "text-score-mid"
                            : "text-score-low"
                      }`}
                    >
                      {startup.ai_review.overall_score}
                    </span>
                  </div>
                </div>

                <div>
                  <h4 className="text-sm font-medium text-text-secondary mb-1">Investment Thesis</h4>
                  <p className="text-sm text-text-primary leading-relaxed">{startup.ai_review.investment_thesis}</p>
                </div>

                {startup.ai_review.dimension_scores.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-medium text-text-secondary mb-1">Dimension Scores</h4>
                    {startup.ai_review.dimension_scores.map((ds) => (
                      <div key={ds.dimension_name}>
                        <ScoreBar score={ds.score} label={ds.dimension_name} />
                        <p className="text-xs text-text-tertiary ml-[calc(10rem+0.75rem)] mt-0.5">{ds.reasoning}</p>
                      </div>
                    ))}
                  </div>
                )}

                <div>
                  <h4 className="text-sm font-medium text-text-secondary mb-1">Key Risks</h4>
                  <p className="text-sm text-text-primary leading-relaxed">{startup.ai_review.key_risks}</p>
                </div>

                <div>
                  <h4 className="text-sm font-medium text-text-secondary mb-1">Verdict</h4>
                  <p className="text-sm text-text-primary leading-relaxed font-medium">{startup.ai_review.verdict}</p>
                </div>

                <p className="text-xs text-text-tertiary">
                  Generated {new Date(startup.ai_review.created_at).toLocaleDateString()}
                </p>
              </section>
            )}

            {/* 4. Founders */}
            {startup.founders.length > 0 && (
              <section>
                <h3 className="font-serif text-lg text-text-primary mb-3">Founders</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {startup.founders.map((f) => (
                    <div key={f.id} className="rounded border border-border bg-surface p-4">
                      <p className="text-sm font-medium text-text-primary">{f.name}</p>
                      {f.title && <p className="text-xs text-text-secondary mt-0.5">{f.title}</p>}
                      {f.linkedin_url && (
                        <a
                          href={f.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent hover:underline mt-1 inline-block"
                        >
                          LinkedIn
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* 5. Funding Rounds */}
            {startup.funding_rounds.length > 0 && (
              <section>
                <h3 className="font-serif text-lg text-text-primary mb-3">Funding Rounds</h3>
                <div className="rounded border border-border overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-hover-row text-text-tertiary text-xs">
                        <th className="text-left py-2 px-4 font-medium">Round</th>
                        <th className="text-left py-2 px-4 font-medium">Amount</th>
                        <th className="text-left py-2 px-4 font-medium">Date</th>
                        <th className="text-left py-2 px-4 font-medium">Lead Investor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {startup.funding_rounds.map((fr) => (
                        <tr key={fr.id} className="border-t border-border">
                          <td className="py-2 px-4 text-text-primary">{fr.round_name}</td>
                          <td className="py-2 px-4 text-text-secondary">{fr.amount || "—"}</td>
                          <td className="py-2 px-4 text-text-secondary">{fr.date || "—"}</td>
                          <td className="py-2 px-4 text-text-secondary">{fr.lead_investor || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* 6. Company Intel */}
            {startup.enrichment_status === "complete" && (
              <section>
                <h3 className="font-serif text-lg text-text-primary mb-3">Company Intel</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {startup.employee_count && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Employees</p>
                      <p className="text-sm text-text-primary">{startup.employee_count}</p>
                    </div>
                  )}
                  {startup.total_funding && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Total Funding</p>
                      <p className="text-sm text-text-primary">{startup.total_funding}</p>
                    </div>
                  )}
                  {startup.founded_date && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Founded</p>
                      <p className="text-sm text-text-primary">{startup.founded_date}</p>
                    </div>
                  )}
                  {startup.key_metrics && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Key Metrics</p>
                      <p className="text-sm text-text-primary whitespace-pre-line">{startup.key_metrics}</p>
                    </div>
                  )}
                  {startup.competitors && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Competitors</p>
                      <p className="text-sm text-text-primary whitespace-pre-line">{startup.competitors}</p>
                    </div>
                  )}
                  {startup.tech_stack && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Tech Stack</p>
                      <p className="text-sm text-text-primary whitespace-pre-line">{startup.tech_stack}</p>
                    </div>
                  )}
                  {startup.hiring_signals && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Hiring Signals</p>
                      <p className="text-sm text-text-primary whitespace-pre-line">{startup.hiring_signals}</p>
                    </div>
                  )}
                  {startup.patents && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Patents</p>
                      <p className="text-sm text-text-primary whitespace-pre-line">{startup.patents}</p>
                    </div>
                  )}
                  {(startup.linkedin_url || startup.twitter_url || startup.crunchbase_url) && (
                    <div className="rounded border border-border bg-surface p-4">
                      <p className="text-xs text-text-tertiary mb-1">Social Links</p>
                      <div className="flex flex-col gap-1">
                        {startup.linkedin_url && (
                          <a href={startup.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-sm text-accent hover:underline">
                            LinkedIn
                          </a>
                        )}
                        {startup.twitter_url && (
                          <a href={startup.twitter_url} target="_blank" rel="noopener noreferrer" className="text-sm text-accent hover:underline">
                            Twitter / X
                          </a>
                        )}
                        {startup.crunchbase_url && (
                          <a href={startup.crunchbase_url} target="_blank" rel="noopener noreferrer" className="text-sm text-accent hover:underline">
                            Crunchbase
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* 7. HR divider */}
            <hr className="border-border" />

            {/* 8. Edit Startup */}
            <section>
              <h3 className="text-lg font-medium text-text-primary mb-3">Edit Startup</h3>
              <StartupEditor
                initial={{
                  name: startup.name,
                  description: startup.description,
                  website_url: startup.website_url,
                  stage: startup.stage,
                  status: startup.status,
                  location_city: startup.location_city,
                  location_state: startup.location_state,
                  location_country: startup.location_country || "US",
                }}
                onSave={async (data) => {
                  await adminApi.updateStartup(session.backendToken!, id, data);
                  loadAll();
                }}
              />
            </section>

            {/* 9. HR divider */}
            <hr className="border-border" />

            {/* 10. DimensionManager */}
            <section>
              <DimensionManager
                dimensions={dimensions}
                templates={templates}
                onApplyTemplate={async (templateId) => {
                  const result = await adminApi.applyTemplate(session.backendToken!, id, templateId);
                  setDimensions(result.dimensions);
                }}
                onSaveDimensions={async (dims) => {
                  const result = await adminApi.updateDimensions(session.backendToken!, id, dims);
                  setDimensions(result);
                }}
              />
            </section>

            {/* 11. HR divider */}
            <hr className="border-border" />

            {/* 12. ExpertPicker */}
            <section>
              <ExpertPicker
                experts={experts}
                assignments={assignments}
                onAssign={async (expertId) => {
                  await adminApi.assignExpert(session.backendToken!, id, expertId);
                  loadAll();
                }}
                onRemoveAssignment={async (assignmentId) => {
                  await adminApi.deleteAssignment(session.backendToken!, assignmentId);
                  loadAll();
                }}
              />
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
