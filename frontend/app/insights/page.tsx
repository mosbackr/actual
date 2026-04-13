"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import type { Industry, Stage, RegionalInsights, RegionMetrics } from "@/lib/types";
import { WorldMap } from "@/components/WorldMap";
import { USMap } from "@/components/USMap";

type MetricKey = "avg_ai_score" | "avg_expert_score" | "avg_user_score";

const METRIC_OPTIONS: { value: MetricKey; label: string; color: string }[] = [
  { value: "avg_ai_score", label: "AI Score", color: "#B8553A" },
  { value: "avg_expert_score", label: "Contributor Score", color: "#2D6A4F" },
  { value: "avg_user_score", label: "Community Score", color: "#B8860B" },
];

const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa",
  KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont",
  VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin",
  WY: "Wyoming", DC: "District of Columbia",
};

const COUNTRY_NAMES: Record<string, string> = {
  AF: "Afghanistan", AL: "Albania", DZ: "Algeria", AO: "Angola", AR: "Argentina",
  AU: "Australia", AT: "Austria", BD: "Bangladesh", BE: "Belgium", BR: "Brazil",
  BG: "Bulgaria", CA: "Canada", CL: "Chile", CN: "China", CO: "Colombia",
  CR: "Costa Rica", CZ: "Czechia", DK: "Denmark", EG: "Egypt", EE: "Estonia",
  FI: "Finland", FR: "France", DE: "Germany", GH: "Ghana", GR: "Greece",
  HU: "Hungary", IS: "Iceland", IN: "India", ID: "Indonesia", IE: "Ireland",
  IL: "Israel", IT: "Italy", JP: "Japan", KE: "Kenya", KR: "South Korea",
  MX: "Mexico", NL: "Netherlands", NZ: "New Zealand", NG: "Nigeria", NO: "Norway",
  PK: "Pakistan", PE: "Peru", PH: "Philippines", PL: "Poland", PT: "Portugal",
  RO: "Romania", RU: "Russia", SA: "Saudi Arabia", SG: "Singapore", ZA: "South Africa",
  ES: "Spain", SE: "Sweden", CH: "Switzerland", TH: "Thailand", TR: "Turkey",
  UA: "Ukraine", AE: "UAE", GB: "United Kingdom", US: "United States",
  VN: "Vietnam",
};

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-tertiary";
  if (score >= 70) return "text-score-high";
  if (score >= 40) return "text-score-mid";
  return "text-score-low";
}

function fmt(v: number | null): string {
  return v !== null ? v.toFixed(1) : "—";
}

function delta(region: number | null, sitewide: number | null): string {
  if (region === null || sitewide === null) return "";
  const d = region - sitewide;
  if (d === 0) return "";
  return d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1);
}

function deltaColor(region: number | null, sitewide: number | null): string {
  if (region === null || sitewide === null) return "";
  const d = region - sitewide;
  if (d > 2) return "text-score-high";
  if (d < -2) return "text-score-low";
  return "text-text-tertiary";
}

function regionDisplayName(code: string): string {
  return STATE_NAMES[code] || COUNTRY_NAMES[code] || code;
}

/* ── Multi-select dropdown ── */
function MultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const toggle = (val: string) => {
    onChange(
      selected.includes(val)
        ? selected.filter((v) => v !== val)
        : [...selected, val]
    );
  };

  const displayText =
    selected.length === 0
      ? label
      : selected.length <= 2
        ? options.filter((o) => selected.includes(o.value)).map((o) => o.label).join(", ")
        : `${selected.length} selected`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 rounded border px-3 py-2 text-sm outline-none transition ${
          selected.length > 0
            ? "border-accent bg-accent/5 text-accent"
            : "border-border bg-surface text-text-primary"
        }`}
      >
        <span className="max-w-[180px] truncate">{displayText}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-56 max-h-64 overflow-y-auto rounded border border-border bg-surface shadow-lg">
          {selected.length > 0 && (
            <button
              onClick={() => { onChange([]); }}
              className="w-full px-3 py-2 text-left text-xs text-accent hover:bg-hover-row transition border-b border-border"
            >
              Clear all
            </button>
          )}
          {options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-hover-row cursor-pointer transition"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
                className="accent-accent"
              />
              {opt.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export default function InsightsPage() {
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [selectedStages, setSelectedStages] = useState<string[]>([]);
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [data, setData] = useState<RegionalInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [metric, setMetric] = useState<MetricKey>("avg_ai_score");
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getIndustries(), api.getStages()]).then(([ind, stg]) => {
      setIndustries(ind);
      setStages(stg);
    });
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    selectedStages.forEach((s) => params.append("stage", s));
    selectedIndustries.forEach((i) => params.append("industry", i));
    try {
      const result = await api.getRegionalInsights(params.toString() ? params : undefined);
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [selectedStages, selectedIndustries]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Combined regions for chart and table: US states + non-US countries
  const allRegions = useMemo(() => {
    if (!data) return [];
    const nonUS = data.countries.filter((c) => c.region !== "US");
    return [...data.us_states, ...nonUS];
  }, [data]);

  const chartData = useMemo(() => {
    return [...allRegions]
      .filter((r) => r[metric] !== null)
      .sort((a, b) => (b[metric] ?? 0) - (a[metric] ?? 0))
      .slice(0, 25)
      .map((r) => ({
        name: STATE_NAMES[r.region] || COUNTRY_NAMES[r.region] || r.region,
        code: r.region,
        score: r[metric],
        count: r.count,
      }));
  }, [allRegions, metric]);

  const selectedData = selectedRegion
    ? allRegions.find((r) => r.region === selectedRegion)
    : null;

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="font-serif text-3xl text-text-primary">Regional Insights</h1>
        <p className="text-text-secondary mt-1">
          Startup scoring metrics by region, compared to sitewide performance.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-8">
        <MultiSelect
          label="All Stages"
          options={stages.map((s) => ({ value: s.value, label: s.label }))}
          selected={selectedStages}
          onChange={setSelectedStages}
        />
        <MultiSelect
          label="All Verticals"
          options={industries.map((i) => ({ value: i.slug, label: i.name }))}
          selected={selectedIndustries}
          onChange={setSelectedIndustries}
        />

        {(selectedStages.length > 0 || selectedIndustries.length > 0) && (
          <button
            onClick={() => { setSelectedStages([]); setSelectedIndustries([]); }}
            className="text-xs text-accent hover:text-accent-hover transition"
          >
            Clear all filters
          </button>
        )}

        {/* Metric toggle */}
        <div className="flex items-center gap-1 ml-auto rounded border border-border bg-surface p-0.5">
          {METRIC_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setMetric(opt.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded transition ${
                metric === opt.value
                  ? "bg-accent text-white"
                  : "text-text-tertiary hover:text-text-secondary"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-20 text-text-tertiary text-sm">Loading regional data...</div>
      ) : !data || (data.countries.length === 0 && data.us_states.length === 0) ? (
        <div className="text-center py-20 text-text-tertiary text-sm">No regional data available for the selected filters.</div>
      ) : (
        <>
          {/* Sitewide summary bar */}
          <div className="grid grid-cols-4 gap-4 mb-8">
            <div className="rounded border border-border bg-surface p-4">
              <p className="text-xs text-text-tertiary mb-1">Total Startups</p>
              <p className="font-serif text-2xl text-text-primary tabular-nums">{data.sitewide.count}</p>
            </div>
            <div className="rounded border border-border bg-surface p-4">
              <p className="text-xs text-text-tertiary mb-1">Avg AI Score</p>
              <p className={`font-serif text-2xl tabular-nums ${scoreColor(data.sitewide.avg_ai_score)}`}>
                {fmt(data.sitewide.avg_ai_score)}
              </p>
            </div>
            <div className="rounded border border-border bg-surface p-4">
              <p className="text-xs text-text-tertiary mb-1">Avg Contributor</p>
              <p className={`font-serif text-2xl tabular-nums ${scoreColor(data.sitewide.avg_expert_score)}`}>
                {fmt(data.sitewide.avg_expert_score)}
              </p>
            </div>
            <div className="rounded border border-border bg-surface p-4">
              <p className="text-xs text-text-tertiary mb-1">Avg Community</p>
              <p className={`font-serif text-2xl tabular-nums ${scoreColor(data.sitewide.avg_user_score)}`}>
                {fmt(data.sitewide.avg_user_score)}
              </p>
            </div>
          </div>

          {/* Side-by-side maps */}
          <section className="mb-8">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* US Map */}
              <div className="rounded border border-border bg-surface p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-medium text-text-primary">
                    United States — {METRIC_OPTIONS.find((o) => o.value === metric)?.label}
                  </h2>
                  {selectedRegion && STATE_NAMES[selectedRegion] && (
                    <button
                      onClick={() => setSelectedRegion(null)}
                      className="text-xs text-accent hover:text-accent-hover transition"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <USMap
                  regions={data.us_states}
                  metric={metric}
                  selectedRegion={selectedRegion}
                  onSelectRegion={setSelectedRegion}
                />
                <div className="flex items-center justify-center gap-4 mt-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: "#E8E6E3" }} />
                    <span className="text-xs text-text-tertiary">No data</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: "#D4B8A8" }} />
                    <span className="text-xs text-text-tertiary">Low</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: "#B8553A" }} />
                    <span className="text-xs text-text-tertiary">High</span>
                  </div>
                </div>
              </div>

              {/* World Map */}
              <div className="rounded border border-border bg-surface p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-medium text-text-primary">
                    Worldwide — {METRIC_OPTIONS.find((o) => o.value === metric)?.label}
                  </h2>
                  {selectedRegion && COUNTRY_NAMES[selectedRegion] && !STATE_NAMES[selectedRegion] && (
                    <button
                      onClick={() => setSelectedRegion(null)}
                      className="text-xs text-accent hover:text-accent-hover transition"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <WorldMap
                  regions={data.countries}
                  metric={metric}
                  selectedRegion={selectedRegion}
                  onSelectRegion={setSelectedRegion}
                />
                <div className="flex items-center justify-center gap-4 mt-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: "#E8E6E3" }} />
                    <span className="text-xs text-text-tertiary">No data</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: "#D4B8A8" }} />
                    <span className="text-xs text-text-tertiary">Low</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: "#B8553A" }} />
                    <span className="text-xs text-text-tertiary">High</span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Selected region detail */}
          {selectedData && (
            <section className="mb-8">
              <div className="rounded border-2 border-accent bg-surface p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-serif text-lg text-text-primary">{regionDisplayName(selectedData.region)}</h3>
                  <span className="text-xs text-text-tertiary">{selectedData.count} startup{selectedData.count !== 1 ? "s" : ""}</span>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  {METRIC_OPTIONS.map((opt) => {
                    const regionVal = selectedData[opt.value];
                    const siteVal = data.sitewide[opt.value];
                    const d = delta(regionVal, siteVal);
                    return (
                      <div key={opt.value}>
                        <p className="text-xs text-text-tertiary mb-1">{opt.label}</p>
                        <p className={`font-serif text-xl tabular-nums ${scoreColor(regionVal)}`}>
                          {fmt(regionVal)}
                          {d && (
                            <span className={`text-xs ml-1.5 ${deltaColor(regionVal, siteVal)}`}>
                              {d} vs site
                            </span>
                          )}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            </section>
          )}

          {/* Bar chart */}
          {chartData.length > 0 && (
            <section className="mb-8">
              <h2 className="text-sm font-medium text-text-primary mb-3">
                Top Regions — {METRIC_OPTIONS.find((o) => o.value === metric)?.label}
              </h2>
              <div className="rounded border border-border bg-surface p-4">
                <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 28)}>
                  <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} stroke="#9B9B9B" fontSize={11} />
                    <YAxis type="category" dataKey="name" width={120} stroke="#9B9B9B" fontSize={11} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#FFFFFF",
                        border: "1px solid #E8E6E3",
                        borderRadius: "4px",
                        color: "#1A1A1A",
                        fontSize: "12px",
                      }}
                      formatter={(value) => [Number(value).toFixed(1), "Score"]}
                    />
                    <Bar
                      dataKey="score"
                      fill={METRIC_OPTIONS.find((o) => o.value === metric)?.color || "#B8553A"}
                      radius={[0, 3, 3, 0]}
                    />
                    {data.sitewide[metric] !== null && (
                      <ReferenceLine
                        x={data.sitewide[metric]!}
                        stroke="#9B9B9B"
                        strokeDasharray="4 4"
                        label={{ value: "Sitewide", position: "top", fill: "#9B9B9B", fontSize: 10 }}
                      />
                    )}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          {/* Summary table */}
          <section className="mb-12">
            <h2 className="text-sm font-medium text-text-primary mb-3">All Regions</h2>
            <div className="rounded border border-border bg-surface overflow-x-auto">
              <table className="w-full text-sm min-w-[600px]">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Region</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Startups</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">AI Score</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Contributor</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Community</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Sitewide row */}
                  <tr className="border-b border-border bg-background/50 font-medium">
                    <td className="px-4 py-2.5 text-text-primary">Sitewide Average</td>
                    <td className="px-4 py-2.5 text-right text-text-secondary tabular-nums">{data.sitewide.count}</td>
                    <td className={`px-4 py-2.5 text-right tabular-nums ${scoreColor(data.sitewide.avg_ai_score)}`}>{fmt(data.sitewide.avg_ai_score)}</td>
                    <td className={`px-4 py-2.5 text-right tabular-nums ${scoreColor(data.sitewide.avg_expert_score)}`}>{fmt(data.sitewide.avg_expert_score)}</td>
                    <td className={`px-4 py-2.5 text-right tabular-nums ${scoreColor(data.sitewide.avg_user_score)}`}>{fmt(data.sitewide.avg_user_score)}</td>
                  </tr>
                  {[...allRegions].sort((a, b) => (b[metric] ?? 0) - (a[metric] ?? 0)).map((r) => (
                    <tr
                      key={r.region}
                      className={`border-b border-border last:border-b-0 cursor-pointer transition ${
                        selectedRegion === r.region ? "bg-accent/5" : "hover:bg-hover-row"
                      }`}
                      onClick={() => setSelectedRegion(selectedRegion === r.region ? null : r.region)}
                    >
                      <td className="px-4 py-2.5 text-text-primary font-medium">{regionDisplayName(r.region)}</td>
                      <td className="px-4 py-2.5 text-right text-text-secondary tabular-nums">{r.count}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        <span className={scoreColor(r.avg_ai_score)}>{fmt(r.avg_ai_score)}</span>
                        {r.avg_ai_score !== null && data.sitewide.avg_ai_score !== null && (
                          <span className={`text-xs ml-1 ${deltaColor(r.avg_ai_score, data.sitewide.avg_ai_score)}`}>
                            {delta(r.avg_ai_score, data.sitewide.avg_ai_score)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        <span className={scoreColor(r.avg_expert_score)}>{fmt(r.avg_expert_score)}</span>
                        {r.avg_expert_score !== null && data.sitewide.avg_expert_score !== null && (
                          <span className={`text-xs ml-1 ${deltaColor(r.avg_expert_score, data.sitewide.avg_expert_score)}`}>
                            {delta(r.avg_expert_score, data.sitewide.avg_expert_score)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        <span className={scoreColor(r.avg_user_score)}>{fmt(r.avg_user_score)}</span>
                        {r.avg_user_score !== null && data.sitewide.avg_user_score !== null && (
                          <span className={`text-xs ml-1 ${deltaColor(r.avg_user_score, data.sitewide.avg_user_score)}`}>
                            {delta(r.avg_user_score, data.sitewide.avg_user_score)}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
