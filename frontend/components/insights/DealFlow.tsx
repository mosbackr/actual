"use client";

import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { DealFlowData } from "@/lib/insights-types";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
  public: "Public",
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function formatMonth(monthStr: string): string {
  const [year, month] = monthStr.split("-");
  const date = new Date(Number(year), Number(month) - 1);
  const m = date.toLocaleString("en-US", { month: "short" });
  return `${m} '${year.slice(2)}`;
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-tertiary";
  if (score >= 70) return "text-score-high";
  if (score >= 40) return "text-score-mid";
  return "text-score-low";
}

interface Props {
  data: DealFlowData;
}

export function DealFlow({ data }: Props) {
  const chartData = data.monthly.map((m) => ({
    name: formatMonth(m.month),
    count: m.count,
  }));

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Deal Flow</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">New Startups per Month</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" horizontal />
              <XAxis dataKey="name" stroke="#9B9B9B" fontSize={10} />
              <YAxis stroke="#9B9B9B" fontSize={11} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  border: "1px solid #E8E6E3",
                  borderRadius: "4px",
                  color: "#1A1A1A",
                  fontSize: "12px",
                }}
                formatter={(value) => [String(value), "Startups added"]}
              />
              <Bar dataKey="count" fill="#B8553A" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">Recently Added</h3>
          {data.recent.length === 0 ? (
            <p className="text-sm text-text-tertiary py-8 text-center">No recent startups</p>
          ) : (
            <div className="space-y-0">
              {data.recent.map((startup) => (
                <div
                  key={startup.slug}
                  className="flex items-center justify-between py-3 border-b border-border last:border-b-0"
                >
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/startups/${startup.slug}`}
                      className="text-sm font-medium text-accent hover:text-accent-hover transition truncate block"
                    >
                      {startup.name}
                    </Link>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-text-tertiary">{startup.industry}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-background text-text-secondary">
                        {STAGE_LABELS[startup.stage] || startup.stage}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    {startup.ai_score !== null && (
                      <span className={`text-sm font-medium tabular-nums ${scoreColor(startup.ai_score)}`}>
                        {startup.ai_score.toFixed(0)}
                      </span>
                    )}
                    <span className="text-xs text-text-tertiary w-12 text-right">
                      {timeAgo(startup.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
