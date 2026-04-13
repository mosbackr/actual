"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { InsightsResponse } from "@/lib/insights-types";
import { InsightsSummary } from "@/components/insights/InsightsSummary";
import { InsightsFilters, type FilterState } from "@/components/insights/InsightsFilters";
import { ScoreLandscape } from "@/components/insights/ScoreLandscape";
import { FundingOverview } from "@/components/insights/FundingOverview";
import { IndustryComparison } from "@/components/insights/IndustryComparison";
import { DealFlow } from "@/components/insights/DealFlow";

function parseFiltersFromParams(params: URLSearchParams): FilterState {
  return {
    stages: params.get("stage")?.split(",").filter(Boolean) || [],
    industries: params.get("industry")?.split(",").filter(Boolean) || [],
    countries: params.get("country")?.split(",").filter(Boolean) || [],
    states: params.get("state")?.split(",").filter(Boolean) || [],
    scoreMin: Number(params.get("score_min") || 0),
    scoreMax: Number(params.get("score_max") || 100),
    dateRange: params.get("date_range") || "all",
  };
}

function filtersToParams(filters: FilterState): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.stages.length) params.set("stage", filters.stages.join(","));
  if (filters.industries.length) params.set("industry", filters.industries.join(","));
  if (filters.countries.length) params.set("country", filters.countries.join(","));
  if (filters.states.length) params.set("state", filters.states.join(","));
  if (filters.scoreMin > 0) params.set("score_min", String(filters.scoreMin));
  if (filters.scoreMax < 100) params.set("score_max", String(filters.scoreMax));
  if (filters.dateRange !== "all") params.set("date_range", filters.dateRange);
  return params;
}

export default function InsightsDashboard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<FilterState>(() =>
    parseFiltersFromParams(searchParams)
  );
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const isFiltered =
    filters.stages.length > 0 ||
    filters.industries.length > 0 ||
    filters.countries.length > 0 ||
    filters.states.length > 0 ||
    filters.scoreMin > 0 ||
    filters.scoreMax < 100 ||
    filters.dateRange !== "all";

  const fetchData = useCallback(async (f: FilterState) => {
    setLoading(true);
    try {
      const params = filtersToParams(f);
      const result = await api.getInsights(params.toString() ? params : undefined);
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilterChange = (newFilters: FilterState) => {
    setFilters(newFilters);
    const params = filtersToParams(newFilters);
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : "/insights", { scroll: false });
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchData(newFilters), 300);
  };

  const handleIndustryClick = (slug: string) => {
    const newFilters = { ...filters, industries: [slug] };
    handleFilterChange(newFilters);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="font-serif text-3xl text-text-primary">Insights</h1>
        <p className="text-text-secondary mt-1">
          Explore deal flow, scores, and funding across the platform.
        </p>
      </div>

      {loading && !data ? (
        <div className="text-center py-20 text-text-tertiary text-sm">Loading insights...</div>
      ) : data ? (
        <>
          <InsightsSummary data={data.summary} isFiltered={isFiltered} />

          <div className="mt-6">
            <InsightsFilters
              filters={filters}
              filterOptions={data.filters}
              filteredCount={data.summary.filtered_startups}
              totalCount={data.summary.total_startups}
              onChange={handleFilterChange}
            />
          </div>

          <div className="mt-8 space-y-10">
            <ScoreLandscape data={data.scores} />
            <FundingOverview data={data.funding} />
            <IndustryComparison
              data={data.industries}
              onIndustryClick={handleIndustryClick}
            />
            <DealFlow data={data.deal_flow} />
          </div>
        </>
      ) : (
        <div className="text-center py-20 text-text-tertiary text-sm">
          Failed to load insights data.
        </div>
      )}
    </div>
  );
}
