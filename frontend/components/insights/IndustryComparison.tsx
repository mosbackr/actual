"use client";

import { useState } from "react";
import type { IndustryRow } from "@/lib/insights-types";

type SortKey = "avg_ai_score" | "count" | "total_funding";

function formatFunding(val: number): string {
  if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(0)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}K`;
  if (val > 0) return `$${val}`;
  return "\u2014";
}

interface Props {
  data: IndustryRow[];
  onIndustryClick: (slug: string) => void;
}

export function IndustryComparison({ data, onIndustryClick }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("avg_ai_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sorted = [...data].sort((a, b) => {
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    return sortDir === "desc" ? bv - av : av - bv;
  });

  const maxScore = Math.max(...data.map((d) => d.avg_ai_score ?? 0), 1);

  const sortArrow = (key: SortKey) => {
    if (sortKey !== key) return "";
    return sortDir === "desc" ? " \u2193" : " \u2191";
  };

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Industry Comparison</h2>
      <div className="rounded border border-border bg-surface overflow-x-auto">
        <table className="w-full text-sm min-w-[600px]">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary w-48">
                Industry
              </th>
              <th
                className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary cursor-pointer hover:text-text-secondary transition"
                onClick={() => toggleSort("avg_ai_score")}
              >
                Avg AI Score{sortArrow("avg_ai_score")}
              </th>
              <th
                className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary cursor-pointer hover:text-text-secondary transition"
                onClick={() => toggleSort("count")}
              >
                Startups{sortArrow("count")}
              </th>
              <th
                className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary cursor-pointer hover:text-text-secondary transition"
                onClick={() => toggleSort("total_funding")}
              >
                Total Funding{sortArrow("total_funding")}
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr
                key={row.slug}
                className="border-b border-border last:border-b-0 hover:bg-hover-row transition cursor-pointer"
                onClick={() => onIndustryClick(row.slug)}
              >
                <td className="px-4 py-2.5 text-text-primary font-medium">{row.name}</td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-4 bg-background rounded overflow-hidden">
                      <div
                        className="h-full bg-accent rounded"
                        style={{ width: `${((row.avg_ai_score ?? 0) / maxScore) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-text-primary tabular-nums w-8 text-right">
                      {row.avg_ai_score !== null ? row.avg_ai_score.toFixed(1) : "\u2014"}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-2.5 text-right text-text-secondary tabular-nums">{row.count}</td>
                <td className="px-4 py-2.5 text-right text-text-secondary tabular-nums">
                  {formatFunding(row.total_funding)}
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">
                  No industry data
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
