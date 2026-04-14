"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { FundingData } from "@/lib/insights-types";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatFundingDate(raw?: string | null): string {
  if (!raw) return "\u2014";
  const isoMatch = raw.match(/^(\d{4})-(\d{2})(?:-\d{2})?$/);
  if (isoMatch) {
    const month = MONTH_NAMES[parseInt(isoMatch[2], 10) - 1];
    return month ? `${month} ${isoMatch[1]}` : raw;
  }
  const qMatch = raw.match(/^(\d{4})-(Q\d)$/i);
  if (qMatch) return `${qMatch[2].toUpperCase()} ${qMatch[1]}`;
  return raw;
}

function formatAmount(val: number): string {
  if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(0)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}K`;
  return `$${val}`;
}

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
  data: FundingData;
}

export function FundingOverview({ data }: Props) {
  const [mode, setMode] = useState<"amount" | "count">("amount");

  const chartData = data.by_stage.map((s) => ({
    name: s.label,
    value: mode === "amount" ? s.total_amount : s.count,
  }));

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Funding Overview</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-surface p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-text-primary">Funding by Stage</h3>
            <div className="flex items-center gap-1 rounded border border-border bg-background p-0.5">
              <button
                onClick={() => setMode("amount")}
                className={`px-3 py-1 text-xs font-medium rounded transition ${
                  mode === "amount" ? "bg-accent text-white" : "text-text-tertiary hover:text-text-secondary"
                }`}
              >
                $ Amount
              </button>
              <button
                onClick={() => setMode("count")}
                className={`px-3 py-1 text-xs font-medium rounded transition ${
                  mode === "count" ? "bg-accent text-white" : "text-text-tertiary hover:text-text-secondary"
                }`}
              >
                Count
              </button>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" horizontal />
              <XAxis dataKey="name" stroke="#9B9B9B" fontSize={11} />
              <YAxis
                stroke="#9B9B9B"
                fontSize={11}
                tickFormatter={(v) => mode === "amount" ? formatAmount(v) : v}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  border: "1px solid #E8E6E3",
                  borderRadius: "4px",
                  color: "#1A1A1A",
                  fontSize: "12px",
                }}
                formatter={(value) => [
                  mode === "amount" ? formatAmount(Number(value)) : String(value),
                  mode === "amount" ? "Total Funding" : "Startups",
                ]}
              />
              <Bar dataKey="value" fill="#2D6A4F" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">Recent Rounds</h3>
          {data.recent_rounds.length === 0 ? (
            <p className="text-sm text-text-tertiary py-8 text-center">No funding rounds data</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-3 py-2 text-xs font-medium text-text-tertiary">Company</th>
                    <th className="text-right px-3 py-2 text-xs font-medium text-text-tertiary">Amount</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-text-tertiary">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_rounds.map((round, i) => (
                    <tr key={i} className="border-b border-border last:border-b-0 hover:bg-hover-row transition">
                      <td className="px-3 py-2">
                        <Link
                          href={`/startups/${round.startup_slug}`}
                          className="text-accent hover:text-accent-hover transition"
                        >
                          {round.startup_name}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-right text-text-primary tabular-nums">{round.amount}</td>
                      <td className="px-3 py-2 text-text-secondary">{STAGE_LABELS[round.stage] || round.stage}</td>
                      <td className="px-3 py-2 text-text-tertiary">{formatFundingDate(round.date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
