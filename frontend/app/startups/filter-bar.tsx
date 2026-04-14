"use client";

import { useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
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
        className={`flex items-center gap-2 rounded border px-3 py-1.5 text-xs outline-none transition ${
          selected.length > 0
            ? "border-accent bg-accent/5 text-accent"
            : "border-border bg-surface text-text-primary"
        }`}
      >
        <span className="max-w-[160px] truncate">{displayText}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-52 max-h-64 overflow-y-auto rounded border border-border bg-surface shadow-lg">
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
              className="flex items-center gap-2 px-3 py-1.5 text-xs text-text-primary hover:bg-hover-row cursor-pointer transition"
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

/* ── Investor text search ── */
function InvestorSearch({
  value,
  onSearch,
}: {
  value: string;
  onSearch: (value: string) => void;
}) {
  const [text, setText] = useState(value);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSearch(text.trim());
  }

  function handleClear() {
    setText("");
    onSearch("");
  }

  return (
    <form onSubmit={handleSubmit} className="relative flex items-center">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Investor..."
        className={`rounded border px-3 py-1.5 text-xs outline-none transition w-36 ${
          value
            ? "border-accent bg-accent/5 text-accent placeholder-accent/50"
            : "border-border bg-surface text-text-primary placeholder-text-tertiary"
        } focus:border-accent focus:ring-1 focus:ring-accent`}
      />
      {value && (
        <button
          type="button"
          onClick={handleClear}
          className="absolute right-1.5 text-accent hover:text-accent-hover text-xs"
        >
          ✕
        </button>
      )}
    </form>
  );
}

export default function FilterBar({ industries, stages, regions, investors, currentParams }: Props) {
  const router = useRouter();
  const [search, setSearch] = useState(currentParams.q || "");

  // Parse comma-separated current values
  const activeIndustries = currentParams.industry ? currentParams.industry.split(",") : [];
  const activeStages = currentParams.stage ? currentParams.stage.split(",") : [];
  const activeRegions = currentParams.region ? currentParams.region.split(",") : [];
  const activeInvestors = currentParams.investor ? currentParams.investor.split(",") : [];

  function handleMulti(key: string, values: string[]) {
    const val = values.length > 0 ? values.join(",") : undefined;
    router.push(buildHref(currentParams, { [key]: val, page: undefined, sort: "ai_score" }));
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    router.push(buildHref(currentParams, { q: search || undefined, page: undefined, sort: "ai_score" }));
  }

  return (
    <div className="flex flex-wrap items-center gap-2 mb-6">
      <MultiSelect
        label="All Industries"
        options={industries.map((i) => ({ value: i.slug, label: i.name }))}
        selected={activeIndustries}
        onChange={(vals) => handleMulti("industry", vals)}
      />

      <MultiSelect
        label="All Stages"
        options={stages.map((s) => ({ value: s.value, label: s.label }))}
        selected={activeStages}
        onChange={(vals) => handleMulti("stage", vals)}
      />

      <MultiSelect
        label="All Regions"
        options={regions.map((r) => ({ value: r, label: r }))}
        selected={activeRegions}
        onChange={(vals) => handleMulti("region", vals)}
      />

      <InvestorSearch
        value={currentParams.investor || ""}
        onSearch={(val) => router.push(buildHref(currentParams, { investor: val || undefined, page: undefined, sort: "ai_score" }))}
      />

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
