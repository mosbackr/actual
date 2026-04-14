import Link from "next/link";
import type { PaginatedStartups, Industry, Stage } from "@/lib/types";
import FilterBar from "./filter-bar";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
  public: "Public",
};

interface Filters {
  page: number;
  industry?: string;   // comma-separated slugs
  stage?: string;      // comma-separated values
  region?: string;     // comma-separated values
  investor?: string;
  q?: string;
  sort: string;
}

async function getStartups(filters: Filters): Promise<PaginatedStartups> {
  try {
    const params = new URLSearchParams();
    params.set("page", String(filters.page));
    params.set("per_page", "24");
    // Send multi-values as repeated params for FastAPI
    if (filters.industry) {
      for (const v of filters.industry.split(",")) params.append("industry", v);
    }
    if (filters.stage) {
      for (const v of filters.stage.split(",")) params.append("stage", v);
    }
    if (filters.region) {
      for (const v of filters.region.split(",")) params.append("region", v);
    }
    if (filters.investor) {
      for (const v of filters.investor.split(",")) params.append("investor", v);
    }
    if (filters.q) params.set("q", filters.q);
    if (filters.sort) params.set("sort", filters.sort);

    const res = await fetch(`${API_URL}/api/startups?${params}`, { cache: "no-store" });
    if (!res.ok) return { total: 0, page: 1, per_page: 24, pages: 0, items: [] };
    return res.json();
  } catch {
    return { total: 0, page: 1, per_page: 24, pages: 0, items: [] };
  }
}

async function getFilterOptions(): Promise<{
  industries: Industry[];
  stages: Stage[];
  regions: string[];
  investors: string[];
}> {
  try {
    const [indRes, stageRes, filterRes] = await Promise.all([
      fetch(`${API_URL}/api/industries`, { cache: "no-store" }),
      fetch(`${API_URL}/api/stages`, { cache: "no-store" }),
      fetch(`${API_URL}/api/filters`, { cache: "no-store" }),
    ]);

    const industries = indRes.ok ? await indRes.json() : [];
    const stages = stageRes.ok ? await stageRes.json() : [];
    const filters = filterRes.ok ? await filterRes.json() : { regions: [], investors: [] };

    return { industries, stages, regions: filters.regions, investors: filters.investors };
  } catch {
    return { industries: [], stages: [], regions: [], investors: [] };
  }
}

function buildHref(current: Record<string, string | undefined>, overrides: Record<string, string | undefined>): string {
  const merged = { ...current, ...overrides };
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(merged)) {
    if (v && k !== "page") params.set(k, v);
  }
  if (overrides.page && overrides.page !== "1") params.set("page", overrides.page);
  const qs = params.toString();
  return `/startups${qs ? `?${qs}` : ""}`;
}

export default async function StartupsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const page = Math.max(1, parseInt(params.page || "1", 10));
  const sort = params.sort || "ai_score";

  const [data, filterOptions] = await Promise.all([
    getStartups({
      page,
      industry: params.industry,
      stage: params.stage,
      region: params.region,
      investor: params.investor,
      q: params.q,
      sort,
    }),
    getFilterOptions(),
  ]);

  const currentParams = {
    industry: params.industry,
    stage: params.stage,
    region: params.region,
    investor: params.investor,
    q: params.q,
    sort: params.sort,
  };

  const hasFilters = !!(params.industry || params.stage || params.region || params.investor || params.q);

  // Parse multi-values for display
  const activeIndustries = params.industry ? params.industry.split(",") : [];
  const activeStages = params.stage ? params.stage.split(",") : [];
  const activeRegions = params.region ? params.region.split(",") : [];
  const activeInvestors = params.investor ? params.investor.split(",") : [];

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-serif text-3xl text-text-primary">Venture Backed Companies</h1>
        <p className="text-text-secondary text-sm mt-2">
          {data.total} venture-backed companies tracked
        </p>
      </div>

      {/* Sort tabs */}
      <div className="flex items-center gap-1 mb-4 border-b border-border">
        {[
          { value: "newest", label: "New" },
          { value: "trending", label: "Trending" },
          { value: "ai_score", label: "Top Rated" },
        ].map((tab) => (
          <Link
            key={tab.value}
            href={buildHref(currentParams, { sort: tab.value, page: "1" })}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
              sort === tab.value
                ? "border-accent text-accent"
                : "border-transparent text-text-tertiary hover:text-text-secondary"
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </div>

      {/* Filter bar */}
      <FilterBar
        industries={filterOptions.industries}
        stages={filterOptions.stages}
        regions={filterOptions.regions}
        investors={filterOptions.investors}
        currentParams={currentParams}
      />

      {hasFilters && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <span className="text-xs text-text-tertiary">Active filters:</span>
          {activeIndustries.map((slug) => {
            const remaining = activeIndustries.filter((s) => s !== slug).join(",");
            return (
              <Link
                key={slug}
                href={buildHref(currentParams, { industry: remaining || undefined, page: "1" })}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-accent/10 text-accent hover:bg-accent/20 transition"
              >
                {filterOptions.industries.find((i) => i.slug === slug)?.name || slug}
                <span>&times;</span>
              </Link>
            );
          })}
          {activeStages.map((val) => {
            const remaining = activeStages.filter((s) => s !== val).join(",");
            return (
              <Link
                key={val}
                href={buildHref(currentParams, { stage: remaining || undefined, page: "1" })}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-accent/10 text-accent hover:bg-accent/20 transition"
              >
                {stageLabels[val] || val}
                <span>&times;</span>
              </Link>
            );
          })}
          {activeRegions.map((val) => {
            const remaining = activeRegions.filter((s) => s !== val).join(",");
            return (
              <Link
                key={val}
                href={buildHref(currentParams, { region: remaining || undefined, page: "1" })}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-accent/10 text-accent hover:bg-accent/20 transition"
              >
                {val}
                <span>&times;</span>
              </Link>
            );
          })}
          {activeInvestors.map((val) => {
            const remaining = activeInvestors.filter((s) => s !== val).join(",");
            return (
              <Link
                key={val}
                href={buildHref(currentParams, { investor: remaining || undefined, page: "1" })}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-accent/10 text-accent hover:bg-accent/20 transition"
              >
                {val}
                <span>&times;</span>
              </Link>
            );
          })}
          {params.q && (
            <Link href={buildHref(currentParams, { q: undefined, page: "1" })} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-accent/10 text-accent hover:bg-accent/20 transition">
              &ldquo;{params.q}&rdquo;
              <span>&times;</span>
            </Link>
          )}
          <Link href="/startups" className="text-xs text-text-tertiary hover:text-text-secondary transition ml-1">
            Clear all
          </Link>
        </div>
      )}

      {data.items.length === 0 ? (
        <p className="text-text-tertiary text-sm py-10 text-center">
          {hasFilters ? "No companies match your filters." : "No companies yet."}
        </p>
      ) : (
        <>
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
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs px-2 py-0.5 rounded border border-border text-text-tertiary">
                    {stageLabels[startup.stage] || startup.stage}
                  </span>
                  {startup.industries.length > 0 && (
                    <span className="text-xs text-text-tertiary">
                      {startup.industries[0].name}
                    </span>
                  )}
                  {startup.ai_score != null && (
                    <span className={`text-xs font-medium tabular-nums ml-auto ${
                      startup.ai_score >= 70 ? "text-score-high" : startup.ai_score >= 40 ? "text-score-mid" : "text-score-low"
                    }`}>
                      AI: {startup.ai_score.toFixed(0)}
                    </span>
                  )}
                </div>
                {startup.form_sources?.length > 0 && (
                  <div className="flex gap-1 mt-1.5">
                    {startup.form_sources.map((fs: string) => (
                      <span
                        key={fs}
                        className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-accent/5 text-text-tertiary"
                        title={`Data from ${fs}`}
                      >
                        {fs}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
            ))}
          </div>

          {data.pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-10">
              {page > 1 && (
                <Link
                  href={buildHref(currentParams, { page: String(page - 1) })}
                  className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                >
                  Previous
                </Link>
              )}
              <span className="text-sm text-text-tertiary px-3">
                Page {page} of {data.pages}
              </span>
              {page < data.pages && (
                <Link
                  href={buildHref(currentParams, { page: String(page + 1) })}
                  className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                >
                  Next
                </Link>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
