import { notFound } from "next/navigation";
import type { StartupDetail } from "@/lib/types";
import { ScoreComparison } from "@/components/ScoreComparison";
import { ScoreTimeline } from "@/components/ScoreTimeline";
import { DimensionRadar } from "@/components/DimensionRadar";
import { ReviewSection } from "@/components/ReviewSection";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
  public: "Public",
};

function ScoreBar({ score, label }: { score: number; label: string }) {
  const color = score >= 70 ? "bg-score-high" : score >= 40 ? "bg-score-mid" : "bg-score-low";
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-text-secondary w-48 shrink-0">{label}</span>
      <div className="flex-1 h-2.5 bg-background rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-medium text-text-primary w-8 text-right tabular-nums">{score}</span>
    </div>
  );
}

function SourceBadge({ source }: { source: string | undefined }) {
  if (!source) return null;
  const labels: Record<string, string> = {
    "D": "Form D",
    "S-1": "S-1 Filing",
    "10-K": "10-K Filing",
    "C": "Form C",
    "1-A": "Form 1-A",
    "perplexity": "AI Research",
    "logo.dev": "Logo.dev",
  };
  const colors: Record<string, string> = {
    "D": "bg-amber-500/10 text-amber-400",
    "S-1": "bg-blue-500/10 text-blue-400",
    "10-K": "bg-green-500/10 text-green-400",
    "C": "bg-purple-500/10 text-purple-400",
    "1-A": "bg-cyan-500/10 text-cyan-400",
    "perplexity": "bg-zinc-500/10 text-zinc-400",
    "logo.dev": "bg-zinc-500/10 text-zinc-400",
  };
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded ${colors[source] || "bg-zinc-500/10 text-zinc-400"}`}
      title={labels[source] || source}
    >
      {labels[source] || source}
    </span>
  );
}

async function getStartup(slug: string): Promise<StartupDetail | null> {
  const res = await fetch(`${API_URL}/api/startups/${slug}`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

export default async function StartupPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const startup = await getStartup(slug);
  if (!startup) notFound();

  const hasScoreHistory = startup.score_history && startup.score_history.length > 0;

  return (
    <div className="max-w-4xl mx-auto overflow-hidden">
      {/* Hero */}
      <div className="flex items-start gap-6 mb-12">
        {startup.logo_url ? (
          <img src={startup.logo_url} alt={startup.name} className="h-20 w-20 shrink-0 rounded object-cover" />
        ) : (
          <div className="h-20 w-20 rounded bg-background border border-border flex items-center justify-center font-serif text-2xl text-text-tertiary">
            {startup.name[0]}
          </div>
        )}
        <div className="flex-1">
          <h1 className="font-serif text-3xl text-text-primary">{startup.name}</h1>
          {startup.tagline && (
            <p className="text-text-tertiary mt-1 text-sm">{startup.tagline}</p>
          )}
          {startup.form_sources?.length > 0 && (
            <div className="flex gap-1 mt-1">
              {startup.form_sources.map((fs: string) => (
                <SourceBadge key={fs} source={fs} />
              ))}
            </div>
          )}
          <div className="mt-2">
            <p className="text-text-secondary break-words">{startup.description}</p>
            {startup.data_sources?.description && (
              <SourceBadge source={startup.data_sources.description} />
            )}
          </div>
          <div className="flex flex-wrap gap-2 mt-3 items-center">
            <span className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary">
              {stageLabels[startup.stage] || startup.stage}
            </span>
            {startup.company_status && startup.company_status !== "unknown" && (
              <span className={`rounded border px-3 py-1 text-xs font-medium ${
                startup.company_status === "active" ? "border-score-high/30 text-score-high" :
                startup.company_status === "acquired" ? "border-accent/30 text-accent" :
                startup.company_status === "ipo" ? "border-score-high/30 text-score-high" :
                "border-score-low/30 text-score-low"
              }`}>
                {startup.company_status === "ipo" ? "IPO" : startup.company_status.charAt(0).toUpperCase() + startup.company_status.slice(1)}
              </span>
            )}
            {(startup.location_city || startup.location_country) && (
              <span className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary">
                {[startup.location_city, startup.location_state, startup.location_country].filter(Boolean).join(", ")}
              </span>
            )}
            {startup.total_funding && (
              <span className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary inline-flex items-center gap-1">
                {startup.total_funding} raised
                <SourceBadge source={startup.data_sources?.total_funding} />
              </span>
            )}
            {startup.revenue_estimate && (
              <span className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary inline-flex items-center gap-1">
                {startup.revenue_estimate}
                <SourceBadge source={startup.data_sources?.revenue_estimate} />
              </span>
            )}
            {startup.business_model && (
              <span className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary inline-flex items-center gap-1">
                {startup.business_model}
                <SourceBadge source={startup.data_sources?.business_model} />
              </span>
            )}
            {startup.employee_count && (
              <span className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary inline-flex items-center gap-1">
                {startup.employee_count} employees
                <SourceBadge source={startup.data_sources?.employee_count} />
              </span>
            )}
            {startup.industries.map((ind) => (
              <span key={ind.id} className="rounded px-3 py-1 text-xs text-text-tertiary">{ind.name}</span>
            ))}
          </div>
          <div className="flex flex-wrap gap-3 mt-3 items-center">
            {startup.website_url && (
              <span className="inline-flex items-center gap-1">
                <a href={startup.website_url} target="_blank" rel="noopener noreferrer"
                  className="text-xs text-accent hover:text-accent-hover transition">
                  Website &rarr;
                </a>
                <SourceBadge source={startup.data_sources?.website_url} />
              </span>
            )}
            {startup.linkedin_url && (
              <a href={startup.linkedin_url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-accent hover:text-accent-hover transition">
                LinkedIn &rarr;
              </a>
            )}
            {startup.twitter_url && (
              <a href={startup.twitter_url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-accent hover:text-accent-hover transition">
                Twitter &rarr;
              </a>
            )}
            {startup.crunchbase_url && (
              <a href={startup.crunchbase_url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-accent hover:text-accent-hover transition">
                Crunchbase &rarr;
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Scores Overview */}
      <section className="mb-12">
        <h2 className="font-serif text-xl text-text-primary mb-6">Scores Overview</h2>
        <ScoreComparison aiScore={startup.ai_score} expertScore={startup.expert_score} userScore={startup.user_score} />
      </section>

      {/* Reviews & Scoring */}
      <ReviewSection
        slug={startup.slug}
        dimensions={
          startup.dimensions && startup.dimensions.length > 0
            ? startup.dimensions.map((d) => ({ name: d.name, weight: d.weight }))
            : []
        }
      />

      {/* AI Analysis */}
      {startup.ai_review && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">AI Analysis</h2>
          <div className="rounded border border-border bg-surface p-6 space-y-6">
            {/* Investment Thesis */}
            <div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Investment Thesis</h3>
              <p className="text-sm text-text-secondary whitespace-pre-wrap">{startup.ai_review.investment_thesis}</p>
            </div>

            {/* Dimension Breakdown */}
            {Array.isArray(startup.ai_review.dimension_scores) && startup.ai_review.dimension_scores.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-text-primary mb-3">Dimension Breakdown</h3>
                <div className="space-y-4">
                  {startup.ai_review.dimension_scores.map((ds) => (
                    <div key={ds.dimension_name}>
                      <ScoreBar score={ds.score} label={ds.dimension_name} />
                      <p className="text-xs text-text-tertiary mt-1 ml-[12.75rem]">{ds.reasoning}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key Risks */}
            <div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Key Risks</h3>
              <p className="text-sm text-text-secondary whitespace-pre-wrap">{startup.ai_review.key_risks}</p>
            </div>

            {/* Verdict */}
            <div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Verdict</h3>
              <p className="text-sm text-text-secondary whitespace-pre-wrap">{startup.ai_review.verdict}</p>
            </div>
          </div>
        </section>
      )}

      {/* Score Timeline */}
      {hasScoreHistory && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Score History</h2>
          <div className="rounded border border-border bg-surface p-6">
            <ScoreTimeline history={startup.score_history} />
          </div>
        </section>
      )}

      {/* Dimension Breakdown Radar */}
      {hasScoreHistory && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Dimension Breakdown</h2>
          <div className="rounded border border-border bg-surface p-6">
            <DimensionRadar history={startup.score_history} />
          </div>
        </section>
      )}

      {/* Team */}
      {startup.founders && startup.founders.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Team</h2>
          {/* Founders */}
          {startup.founders.filter(f => f.is_founder !== false).length > 0 && (
            <div className="mb-4">
              <h3 className="text-xs font-medium text-text-tertiary uppercase tracking-wide mb-3">Founders</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {startup.founders.filter(f => f.is_founder !== false).map((f) => (
                  <div key={f.name} className="rounded border border-border bg-surface p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-text-primary">{f.name}</p>
                        {f.title && <p className="text-xs text-text-tertiary mt-0.5">{f.title}</p>}
                      </div>
                      {f.linkedin_url && (
                        <a href={f.linkedin_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-accent hover:text-accent-hover transition">
                          LinkedIn &rarr;
                        </a>
                      )}
                    </div>
                    {f.prior_experience && (
                      <p className="text-xs text-text-secondary mt-2">{f.prior_experience}</p>
                    )}
                    {f.education && (
                      <p className="text-xs text-text-tertiary mt-1">{f.education}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Management Team */}
          {startup.founders.filter(f => f.is_founder === false).length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-text-tertiary uppercase tracking-wide mb-3">Management</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {startup.founders.filter(f => f.is_founder === false).map((f) => (
                  <div key={f.name} className="rounded border border-border bg-surface p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-text-primary">{f.name}</p>
                        {f.title && <p className="text-xs text-text-tertiary mt-0.5">{f.title}</p>}
                      </div>
                      {f.linkedin_url && (
                        <a href={f.linkedin_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-accent hover:text-accent-hover transition">
                          LinkedIn &rarr;
                        </a>
                      )}
                    </div>
                    {f.prior_experience && (
                      <p className="text-xs text-text-secondary mt-2">{f.prior_experience}</p>
                    )}
                    {f.education && (
                      <p className="text-xs text-text-tertiary mt-1">{f.education}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Funding History */}
      {startup.funding_rounds && startup.funding_rounds.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Funding History</h2>
          <div className="rounded border border-border bg-surface overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="border-b border-border bg-background">
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Round</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Amount</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Valuation</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Date</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Investors</th>
                </tr>
              </thead>
              <tbody>
                {startup.funding_rounds.map((fr, i) => (
                  <tr key={i} className="border-b border-border last:border-b-0">
                    <td className="px-4 py-2.5 text-text-primary font-medium">{fr.round_name}</td>
                    <td className="px-4 py-2.5 text-text-secondary">{fr.amount || "—"}</td>
                    <td className="px-4 py-2.5 text-text-secondary">
                      {fr.post_money_valuation || fr.pre_money_valuation
                        ? `${fr.post_money_valuation ? fr.post_money_valuation + " post" : fr.pre_money_valuation + " pre"}`
                        : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-text-secondary">{fr.date || "—"}</td>
                    <td className="px-4 py-2.5 text-text-secondary">
                      {fr.lead_investor && <span className="font-medium">{fr.lead_investor}</span>}
                      {fr.lead_investor && fr.other_investors && <span className="text-text-tertiary">, </span>}
                      {fr.other_investors && <span className="text-text-tertiary">{fr.other_investors}</span>}
                      {!fr.lead_investor && !fr.other_investors && "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Company Intel */}
      {(startup.key_metrics || startup.competitors || startup.tech_stack) && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Company Intel</h2>
          <div className="rounded border border-border bg-surface p-6 space-y-5">
            {startup.key_metrics && (
              <div>
                <div className="flex items-center gap-1.5 mb-1">
                  <h3 className="text-sm font-medium text-text-primary">Key Metrics</h3>
                  <SourceBadge source={startup.data_sources?.key_metrics} />
                </div>
                <p className="text-sm text-text-secondary whitespace-pre-wrap">{startup.key_metrics}</p>
              </div>
            )}
            {startup.competitors && (
              <div>
                <div className="flex items-center gap-1.5 mb-1">
                  <h3 className="text-sm font-medium text-text-primary">Competitors</h3>
                  <SourceBadge source={startup.data_sources?.competitors} />
                </div>
                <p className="text-sm text-text-secondary whitespace-pre-wrap">{startup.competitors}</p>
              </div>
            )}
            {startup.tech_stack && (
              <div>
                <div className="flex items-center gap-1.5 mb-1">
                  <h3 className="text-sm font-medium text-text-primary">Tech Stack</h3>
                  <SourceBadge source={startup.data_sources?.tech_stack} />
                </div>
                <p className="text-sm text-text-secondary whitespace-pre-wrap">{startup.tech_stack}</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Media */}
      {startup.media.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Media Coverage</h2>
          <div className="space-y-3">
            {startup.media.map((m) => (
              <a key={m.id} href={m.url} target="_blank" rel="noopener noreferrer"
                className="block rounded border border-border bg-surface p-4 hover:border-text-tertiary transition">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{m.title}</p>
                    <p className="text-xs text-text-tertiary mt-1">{m.source} &middot; {m.media_type.replace("_", " ")}</p>
                  </div>
                  {m.published_at && (
                    <span className="text-xs text-text-tertiary">{new Date(m.published_at).toLocaleDateString()}</span>
                  )}
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

    </div>
  );
}
