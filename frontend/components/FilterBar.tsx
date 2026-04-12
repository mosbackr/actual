"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { Industry, Stage } from "@/lib/types";
import { api } from "@/lib/api";

export function FilterBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [search, setSearch] = useState(searchParams.get("q") || "");

  useEffect(() => {
    api.getIndustries().then(setIndustries).catch(() => {});
    api.getStages().then(setStages).catch(() => {});
  }, []);

  const updateParams = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
      params.delete("page");
      router.push(`/?${params.toString()}`);
    },
    [router, searchParams]
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    updateParams("q", search);
  };

  const inputClasses =
    "rounded border border-border bg-surface px-4 py-2.5 text-sm text-text-primary placeholder-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

  return (
    <div className="flex flex-col sm:flex-row gap-3 mb-8">
      <form onSubmit={handleSearch} className="flex-1">
        <input
          type="text"
          placeholder="Search companies..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className={`w-full ${inputClasses}`}
        />
      </form>
      <select
        value={searchParams.get("stage") || ""}
        onChange={(e) => updateParams("stage", e.target.value)}
        className={inputClasses}
      >
        <option value="">All Stages</option>
        {stages.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      <select
        value={searchParams.get("industry") || ""}
        onChange={(e) => updateParams("industry", e.target.value)}
        className={inputClasses}
      >
        <option value="">All Industries</option>
        {industries.map((i) => (
          <option key={i.id} value={i.slug}>
            {i.name}
          </option>
        ))}
      </select>
      <select
        value={searchParams.get("sort") || "newest"}
        onChange={(e) => updateParams("sort", e.target.value)}
        className={inputClasses}
      >
        <option value="newest">Newest</option>
        <option value="ai_score">AI Score</option>
        <option value="expert_score">Contributor Score</option>
        <option value="user_score">Community Score</option>
      </select>
    </div>
  );
}
