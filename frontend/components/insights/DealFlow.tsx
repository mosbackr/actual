"use client";

import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { DealFlowData } from "@/lib/insights-types";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatMonth(monthStr: string): string {
  const [year, month] = monthStr.split("-");
  const m = MONTH_NAMES[Number(month) - 1] || month;
  return `${m} '${year.slice(2)}`;
}

function formatFundingDate(raw?: string | null): string {
  if (!raw) return "";
  const isoMatch = raw.match(/^(\d{4})-(\d{2})(?:-\d{2})?$/);
  if (isoMatch) {
    const month = MONTH_NAMES[parseInt(isoMatch[2], 10) - 1];
    return month ? `${month} ${isoMatch[1]}` : raw;
  }
  return raw;
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
          <h3 className="text-sm font-medium text-text-primary mb-3">Funding Rounds per Month</h3>
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
                formatter={(value) => [String(value), "Rounds"]}
              />
              <Bar dataKey="count" fill="#F28C28" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">Recent Funding Rounds</h3>
          {data.recent.length === 0 ? (
            <p className="text-sm text-text-tertiary py-8 text-center">No recent funding rounds</p>
          ) : (
            <div className="space-y-0">
              {data.recent.map((round, i) => (
                <div
                  key={`${round.slug}-${i}`}
                  className="flex items-center justify-between py-3 border-b border-border last:border-b-0"
                >
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/startups/${round.slug}`}
                      className="text-sm font-medium text-accent hover:text-accent-hover transition truncate block"
                    >
                      {round.name}
                    </Link>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-text-tertiary">{round.industry}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-background text-text-secondary">
                        {round.round_name}
                      </span>
                      {round.amount && (
                        <span className="text-xs font-medium text-text-secondary">{round.amount}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    {round.ai_score !== null && (
                      <span className={`text-sm font-medium tabular-nums ${scoreColor(round.ai_score)}`}>
                        {round.ai_score.toFixed(0)}
                      </span>
                    )}
                    <span className="text-xs text-text-tertiary w-16 text-right">
                      {formatFundingDate(round.date)}
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
