"use client";

import { useEffect, useRef, useState } from "react";
import type { FilterOptions } from "@/lib/insights-types";

const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", DC: "District of Columbia",
  FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois",
  IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana",
  ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan",
  MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana",
  NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey",
  NM: "New Mexico", NY: "New York", NC: "North Carolina", ND: "North Dakota",
  OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
  RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee",
  TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington",
  WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
};

const STAGE_OPTIONS = [
  { value: "pre_seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c", label: "Series C" },
  { value: "growth", label: "Growth" },
  { value: "public", label: "Public" },
];

const DATE_OPTIONS = [
  { value: "all", label: "All time" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "6m", label: "Last 6 months" },
  { value: "1y", label: "Last year" },
];

function SingleSelect({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
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

  const current = options.find((o) => o.value === value);
  const isDefault = value === options[0]?.value;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 rounded border px-3 py-2 text-sm outline-none transition ${
          !isDefault
            ? "border-accent bg-accent/5 text-accent"
            : "border-border bg-surface text-text-primary"
        }`}
      >
        <span>{current?.label || value}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-44 rounded border border-border bg-surface shadow-lg">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full px-3 py-2 text-left text-sm transition ${
                opt.value === value
                  ? "text-accent bg-accent/5"
                  : "text-text-primary hover:bg-hover-row"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

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
              onClick={() => onChange([])}
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

export interface FilterState {
  stages: string[];
  industries: string[];
  countries: string[];
  states: string[];
  scoreMin: number;
  scoreMax: number;
  dateRange: string;
}

interface Props {
  filters: FilterState;
  filterOptions: FilterOptions;
  filteredCount: number;
  totalCount: number;
  onChange: (filters: FilterState) => void;
}

export function InsightsFilters({
  filters,
  filterOptions,
  filteredCount,
  totalCount,
  onChange,
}: Props) {
  const hasFilters =
    filters.stages.length > 0 ||
    filters.industries.length > 0 ||
    filters.countries.length > 0 ||
    filters.states.length > 0 ||
    filters.scoreMin > 0 ||
    filters.scoreMax < 100 ||
    filters.dateRange !== "all";

  const clearAll = () =>
    onChange({
      stages: [],
      industries: [],
      countries: [],
      states: [],
      scoreMin: 0,
      scoreMax: 100,
      dateRange: "all",
    });

  return (
    <div className="sticky top-0 z-40 bg-background border-b border-border py-3">
      <div className="flex flex-wrap items-center gap-3">
        <MultiSelect
          label="State"
          options={filterOptions.available_states
            .filter((s) => STATE_NAMES[s])
            .filter((s, i, arr) => arr.indexOf(s) === i)
            .map((s) => ({ value: s, label: STATE_NAMES[s] || s }))}
          selected={filters.states}
          onChange={(states) => onChange({ ...filters, states })}
        />
        <MultiSelect
          label="Stage"
          options={STAGE_OPTIONS}
          selected={filters.stages}
          onChange={(stages) => onChange({ ...filters, stages })}
        />
        <MultiSelect
          label="Industry"
          options={filterOptions.available_industries.map((i) => ({
            value: i.slug,
            label: i.name,
          }))}
          selected={filters.industries}
          onChange={(industries) => onChange({ ...filters, industries })}
        />

        <div className="flex items-center gap-2 text-sm">
          <span className="text-text-tertiary text-xs">AI Score</span>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.scoreMin}
            onChange={(e) =>
              onChange({ ...filters, scoreMin: Math.max(0, Math.min(100, Number(e.target.value))) })
            }
            className="w-14 rounded border border-border bg-surface px-2 py-1.5 text-sm text-text-primary tabular-nums"
          />
          <span className="text-text-tertiary">–</span>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.scoreMax}
            onChange={(e) =>
              onChange({ ...filters, scoreMax: Math.max(0, Math.min(100, Number(e.target.value))) })
            }
            className="w-14 rounded border border-border bg-surface px-2 py-1.5 text-sm text-text-primary tabular-nums"
          />
        </div>

        <SingleSelect
          options={DATE_OPTIONS}
          value={filters.dateRange}
          onChange={(dateRange) => onChange({ ...filters, dateRange })}
        />

        <div className="ml-auto flex items-center gap-4">
          {hasFilters && (
            <button
              onClick={clearAll}
              className="text-xs text-accent hover:text-accent-hover transition"
            >
              Clear all
            </button>
          )}
          <span className="text-xs text-text-tertiary tabular-nums">
            Showing {filteredCount.toLocaleString()} of {totalCount.toLocaleString()} startups
          </span>
        </div>
      </div>
    </div>
  );
}
