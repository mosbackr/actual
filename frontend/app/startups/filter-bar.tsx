"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Industry, Stage } from "@/lib/types";

interface Props {
  industries: Industry[];
  stages: Stage[];
  regions: string[];
  investors: string[];
  currentParams: Record<string, string | undefined>;
}

function buildHref(current: Record<string, string | undefined>, overrides: Record<string, string | undefined>): string {
  const merged = { ...current, ...overrides };
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(merged)) {
    if (v && k !== "page") params.set(k, v);
  }
  const qs = params.toString();
  return `/startups${qs ? `?${qs}` : ""}`;
}

export default function FilterBar({ industries, stages, regions, investors, currentParams }: Props) {
  const router = useRouter();
  const [search, setSearch] = useState(currentParams.q || "");

  function handleFilter(key: string, value: string) {
    const val = value || undefined;
    router.push(buildHref(currentParams, { [key]: val, page: undefined }));
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    router.push(buildHref(currentParams, { q: search || undefined, page: undefined }));
  }

  const selectClasses =
    "rounded border border-border bg-surface px-3 py-1.5 text-xs text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

  return (
    <div className="flex flex-wrap items-center gap-2 mb-6">
      <select
        value={currentParams.industry || ""}
        onChange={(e) => handleFilter("industry", e.target.value)}
        className={selectClasses}
      >
        <option value="">All Industries</option>
        {industries.map((i) => (
          <option key={i.slug} value={i.slug}>{i.name}</option>
        ))}
      </select>

      <select
        value={currentParams.stage || ""}
        onChange={(e) => handleFilter("stage", e.target.value)}
        className={selectClasses}
      >
        <option value="">All Stages</option>
        {stages.map((s) => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
      </select>

      <select
        value={currentParams.region || ""}
        onChange={(e) => handleFilter("region", e.target.value)}
        className={selectClasses}
      >
        <option value="">All Regions</option>
        {regions.map((r) => (
          <option key={r} value={r}>{r}</option>
        ))}
      </select>

      <select
        value={currentParams.investor || ""}
        onChange={(e) => handleFilter("investor", e.target.value)}
        className={selectClasses}
      >
        <option value="">All Investors</option>
        {investors.map((inv) => (
          <option key={inv} value={inv}>{inv}</option>
        ))}
      </select>

      <form onSubmit={handleSearch} className="flex items-center gap-1 ml-auto">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search..."
          className="rounded border border-border bg-surface px-3 py-1.5 text-xs text-text-primary placeholder-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none w-40"
        />
        <button
          type="submit"
          className="rounded border border-border px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
        >
          Search
        </button>
      </form>
    </div>
  );
}
