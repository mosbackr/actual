import Link from "next/link";
import type { PaginatedStartups } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getFeaturedStartups(): Promise<PaginatedStartups> {
  try {
    const res = await fetch(`${API_URL}/api/startups?per_page=6`, { cache: "no-store" });
    if (!res.ok) return { total: 0, page: 1, per_page: 6, pages: 0, items: [] };
    return res.json();
  } catch {
    return { total: 0, page: 1, per_page: 6, pages: 0, items: [] };
  }
}

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
};

export default async function LandingPage() {
  const data = await getFeaturedStartups();

  return (
    <div className="-mx-6 lg:-mx-8 -mt-12">
      {/* Hero */}
      <section className="px-6 lg:px-8 pt-24 pb-20 text-center">
        <h1 className="font-serif text-5xl md:text-6xl text-text-primary max-w-3xl mx-auto leading-tight">
          Startup intelligence,<br />before the term sheet
        </h1>
        <p className="text-text-secondary text-lg mt-6 max-w-xl mx-auto">
          AI-powered due diligence, expert scoring, and deep research on every startup — so you invest with conviction, not guesswork.
        </p>
        <div className="flex items-center justify-center gap-4 mt-10">
          <Link
            href="/startups"
            className="px-6 py-3 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover transition"
          >
            Explore startups
          </Link>
          <Link
            href="/experts/apply"
            className="px-6 py-3 border border-border text-text-secondary text-sm font-medium rounded hover:border-text-tertiary hover:text-text-primary transition"
          >
            Become an expert
          </Link>
        </div>
      </section>

      {/* How It Works */}
      <section className="px-6 lg:px-8 py-20 border-t border-border">
        <div className="max-w-4xl mx-auto">
          <h2 className="font-serif text-2xl text-text-primary text-center mb-12">
            Three layers of intelligence
          </h2>
          <div className="grid md:grid-cols-3 gap-10">
            <div>
              <div className="w-10 h-10 rounded bg-accent/10 flex items-center justify-center mb-4">
                <span className="font-serif text-accent text-lg">1</span>
              </div>
              <h3 className="text-sm font-medium text-text-primary mb-2">AI Analysis</h3>
              <p className="text-sm text-text-secondary">
                Every startup is automatically enriched with web research — founders, funding, competitors, tech stack — then scored across 8 investment dimensions with a full written memo.
              </p>
            </div>
            <div>
              <div className="w-10 h-10 rounded bg-accent/10 flex items-center justify-center mb-4">
                <span className="font-serif text-accent text-lg">2</span>
              </div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Expert Review</h3>
              <p className="text-sm text-text-secondary">
                Domain experts with industry experience score each startup independently. Their assessments add nuance that AI alone can&apos;t capture — pattern recognition from decades of deals.
              </p>
            </div>
            <div>
              <div className="w-10 h-10 rounded bg-accent/10 flex items-center justify-center mb-4">
                <span className="font-serif text-accent text-lg">3</span>
              </div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Community Signal</h3>
              <p className="text-sm text-text-secondary">
                The broader community weighs in with their own assessments. Aggregate sentiment from founders, operators, and investors surfaces insights that formal analysis misses.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* What You Get */}
      <section className="px-6 lg:px-8 py-20 border-t border-border bg-surface">
        <div className="max-w-4xl mx-auto">
          <h2 className="font-serif text-2xl text-text-primary text-center mb-12">
            Deep research on every company
          </h2>
          <div className="grid md:grid-cols-2 gap-6">
            {[
              { title: "Investment Memo", desc: "AI-generated thesis, key risks, and verdict for every startup — the analysis a junior analyst would spend days writing." },
              { title: "Founder Profiles", desc: "Backgrounds, LinkedIn profiles, and track records for every founding team member, automatically sourced." },
              { title: "Funding History", desc: "Complete funding timeline with round sizes, lead investors, and valuations where available." },
              { title: "Competitive Landscape", desc: "Key competitors, market positioning, and differentiation — understand where the company sits." },
              { title: "Dimension Scoring", desc: "Scores across market opportunity, team, product, traction, business model, moat, financials, and timing." },
              { title: "Media Coverage", desc: "Press mentions, articles, and notable coverage aggregated from across the web." },
            ].map((item) => (
              <div key={item.title} className="rounded border border-border bg-background p-5">
                <h3 className="text-sm font-medium text-text-primary mb-1">{item.title}</h3>
                <p className="text-sm text-text-secondary">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Featured Startups */}
      {data.items.length > 0 && (
        <section className="px-6 lg:px-8 py-20 border-t border-border">
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="font-serif text-2xl text-text-primary">Recently analyzed</h2>
              <Link href="/startups" className="text-sm text-accent hover:text-accent-hover transition">
                View all &rarr;
              </Link>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {data.items.map((startup) => (
                <Link
                  key={startup.id}
                  href={`/startups/${startup.slug}`}
                  className="rounded border border-border bg-surface p-5 hover:border-text-tertiary transition block"
                >
                  <div className="flex items-center gap-3 mb-3">
                    {startup.logo_url ? (
                      <img src={startup.logo_url} alt={startup.name} className="h-10 w-10 rounded object-cover" />
                    ) : (
                      <div className="h-10 w-10 rounded bg-background border border-border flex items-center justify-center font-serif text-lg text-text-tertiary">
                        {startup.name[0]}
                      </div>
                    )}
                    <div className="min-w-0">
                      <h3 className="text-sm font-medium text-text-primary truncate">{startup.name}</h3>
                      {startup.tagline && (
                        <p className="text-xs text-text-tertiary truncate">{startup.tagline}</p>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-text-secondary line-clamp-2 mb-3">{startup.description}</p>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded border border-border text-text-tertiary">
                      {stageLabels[startup.stage] || startup.stage}
                    </span>
                    {startup.ai_score != null && (
                      <span className={`text-xs font-medium tabular-nums ${
                        startup.ai_score >= 70 ? "text-score-high" : startup.ai_score >= 40 ? "text-score-mid" : "text-score-low"
                      }`}>
                        AI: {startup.ai_score.toFixed(0)}
                      </span>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="px-6 lg:px-8 py-20 border-t border-border text-center">
        <h2 className="font-serif text-2xl text-text-primary mb-4">
          Built for investors who do the work
        </h2>
        <p className="text-text-secondary text-sm max-w-md mx-auto mb-8">
          Deep Thesis combines AI research, expert judgment, and community signal into one platform — so every investment decision starts with a real thesis.
        </p>
        <Link
          href="/startups"
          className="inline-block px-6 py-3 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover transition"
        >
          Start exploring
        </Link>
      </section>
    </div>
  );
}
