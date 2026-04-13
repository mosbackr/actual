"use client";

import { useRouter } from "next/navigation";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from "recharts";
import type { ScoresData } from "@/lib/insights-types";

const INDUSTRY_COLORS: Record<string, string> = {
  "AI/ML": "#B8553A",
  "FinTech": "#2D6A4F",
  "BioTech": "#7B2D8E",
  "HealthTech": "#1A6B8A",
  "SaaS": "#B8860B",
  "CleanTech": "#3A7D44",
  "EdTech": "#C2553A",
  "Cybersecurity": "#4A4A8A",
};

const VERDICT_COLORS: Record<string, string> = {
  "Strong Invest": "#1B7340",
  "Invest": "#2D6A4F",
  "Lean Invest": "#5A9E6F",
  "Lean Pass": "#C4883A",
  "Pass": "#B8553A",
  "Strong Pass": "#8B3A2A",
};

function getIndustryColor(industry: string): string {
  return INDUSTRY_COLORS[industry] || "#9B9B9B";
}

interface Props {
  data: ScoresData;
}

export function ScoreLandscape({ data }: Props) {
  const router = useRouter();

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Score Landscape</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Scatter plot — 2 columns wide */}
        <div className="lg:col-span-2 rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">AI Score vs Expert Score</h3>
          <ResponsiveContainer width="100%" height={360}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" />
              <XAxis
                type="number"
                dataKey="ai_score"
                domain={[0, 100]}
                name="AI Score"
                stroke="#9B9B9B"
                fontSize={11}
                label={{ value: "AI Score", position: "bottom", offset: -5, fill: "#9B9B9B", fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey="expert_score"
                domain={[0, 100]}
                name="Expert Score"
                stroke="#9B9B9B"
                fontSize={11}
                label={{ value: "Expert Score", angle: -90, position: "insideLeft", fill: "#9B9B9B", fontSize: 11 }}
              />
              <Tooltip
                content={({ payload }) => {
                  if (!payload || payload.length === 0) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="rounded border border-border bg-surface px-3 py-2 shadow-lg text-xs">
                      <p className="font-medium text-text-primary">{d.name}</p>
                      <p className="text-text-secondary">AI: {d.ai_score} | Expert: {d.expert_score}</p>
                      <p className="text-text-tertiary">{d.industry} · {d.stage}</p>
                      {d.total_funding_raw > 0 && (
                        <p className="text-text-tertiary">
                          Funding: ${d.total_funding_raw >= 1e6 ? `${(d.total_funding_raw / 1e6).toFixed(1)}M` : `${(d.total_funding_raw / 1e3).toFixed(0)}K`}
                        </p>
                      )}
                    </div>
                  );
                }}
              />
              <Scatter
                data={data.scatter}
                onClick={
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  ((entry: any) => {
                    if (entry?.slug) router.push(`/startups/${entry.slug}`);
                  }) as never
                }
                cursor="pointer"
              >
                {data.scatter.map((entry, i) => (
                  <circle
                    key={i}
                    fill={getIndustryColor(entry.industry)}
                    fillOpacity={0.7}
                    r={Math.max(4, Math.min(16, Math.log10(entry.total_funding_raw + 1) * 2))}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          {/* Industry legend */}
          <div className="flex flex-wrap gap-3 mt-3 px-2">
            {Object.entries(INDUSTRY_COLORS).map(([name, color]) => (
              <div key={name} className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-xs text-text-tertiary">{name}</span>
              </div>
            ))}
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: "#9B9B9B" }} />
              <span className="text-xs text-text-tertiary">Other</span>
            </div>
          </div>
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-4">
          {/* Histogram */}
          <div className="rounded border border-border bg-surface p-4 flex-1">
            <h3 className="text-sm font-medium text-text-primary mb-3">AI Score Distribution</h3>
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={data.histogram} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                <XAxis dataKey="bucket" stroke="#9B9B9B" fontSize={9} interval={1} />
                <YAxis stroke="#9B9B9B" fontSize={9} width={30} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#FFFFFF",
                    border: "1px solid #E8E6E3",
                    borderRadius: "4px",
                    color: "#1A1A1A",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="count" fill="#B8553A" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Verdict breakdown */}
          <div className="rounded border border-border bg-surface p-4 flex-1">
            <h3 className="text-sm font-medium text-text-primary mb-3">AI Verdict Breakdown</h3>
            <div className="space-y-2">
              {data.verdicts.map((v) => {
                const maxCount = Math.max(...data.verdicts.map((x) => x.count), 1);
                return (
                  <div key={v.verdict} className="flex items-center gap-2">
                    <span className="text-xs text-text-secondary w-24 truncate">{v.verdict}</span>
                    <div className="flex-1 h-5 bg-background rounded overflow-hidden">
                      <div
                        className="h-full rounded"
                        style={{
                          width: `${(v.count / maxCount) * 100}%`,
                          backgroundColor: VERDICT_COLORS[v.verdict] || "#9B9B9B",
                        }}
                      />
                    </div>
                    <span className="text-xs text-text-tertiary tabular-nums w-8 text-right">
                      {v.count}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
