import type { InsightsSummary as SummaryData } from "@/lib/insights-types";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
  public: "Public",
};

interface Props {
  data: SummaryData;
  isFiltered: boolean;
}

export function InsightsSummary({ data, isFiltered }: Props) {
  const metrics = [
    {
      label: "Total Startups",
      value: data.filtered_startups.toLocaleString(),
      subtitle: isFiltered
        ? `of ${data.total_startups.toLocaleString()}`
        : `+${data.new_this_month} this month`,
    },
    {
      label: "Avg AI Score",
      value: data.avg_ai_score !== null ? data.avg_ai_score.toFixed(1) : "\u2014",
      subtitle: "out of 100",
    },
    {
      label: "Total Funding",
      value: data.total_funding,
      subtitle: isFiltered ? "filtered" : null,
    },
    {
      label: "Industries",
      value: data.industry_count.toString(),
      subtitle: "verticals tracked",
    },
    {
      label: "Top Verdict",
      value: data.top_verdict.verdict || "\u2014",
      subtitle: data.top_verdict.count > 0 ? `${data.top_verdict.count} startups` : null,
    },
    {
      label: "Avg Stage",
      value: data.avg_stage ? STAGE_LABELS[data.avg_stage] || data.avg_stage : "\u2014",
      subtitle: data.median_stage ? `median: ${STAGE_LABELS[data.median_stage] || data.median_stage}` : null,
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="rounded border border-border bg-surface p-4"
        >
          <p className="text-xs text-text-tertiary mb-1">{m.label}</p>
          <p className="font-serif text-2xl text-text-primary tabular-nums truncate">
            {m.value}
          </p>
          {m.subtitle && (
            <p className="text-xs text-text-tertiary mt-0.5">{m.subtitle}</p>
          )}
        </div>
      ))}
    </div>
  );
}
