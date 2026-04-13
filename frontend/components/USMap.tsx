"use client";

import { memo, useState, useCallback } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
} from "react-simple-maps";
import type { RegionMetrics } from "@/lib/types";

const GEO_URL = "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";

const STATE_ABBR: Record<string, string> = {
  Alabama: "AL", Alaska: "AK", Arizona: "AZ", Arkansas: "AR", California: "CA",
  Colorado: "CO", Connecticut: "CT", Delaware: "DE", Florida: "FL", Georgia: "GA",
  Hawaii: "HI", Idaho: "ID", Illinois: "IL", Indiana: "IN", Iowa: "IA",
  Kansas: "KS", Kentucky: "KY", Louisiana: "LA", Maine: "ME", Maryland: "MD",
  Massachusetts: "MA", Michigan: "MI", Minnesota: "MN", Mississippi: "MS",
  Missouri: "MO", Montana: "MT", Nebraska: "NE", Nevada: "NV",
  "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
  "North Carolina": "NC", "North Dakota": "ND", Ohio: "OH", Oklahoma: "OK",
  Oregon: "OR", Pennsylvania: "PA", "Rhode Island": "RI", "South Carolina": "SC",
  "South Dakota": "SD", Tennessee: "TN", Texas: "TX", Utah: "UT", Vermont: "VT",
  Virginia: "VA", Washington: "WA", "West Virginia": "WV", Wisconsin: "WI",
  Wyoming: "WY", "District of Columbia": "DC",
};

const ABBR_TO_NAME: Record<string, string> = Object.fromEntries(
  Object.entries(STATE_ABBR).map(([name, abbr]) => [abbr, name])
);

function scoreToColor(score: number | null, max: number): string {
  if (score === null || max === 0) return "#E8E6E3";
  const t = Math.min(score / max, 1);
  const r = Math.round(232 + (184 - 232) * t);
  const g = Math.round(230 + (85 - 230) * t);
  const b = Math.round(227 + (58 - 227) * t);
  return `rgb(${r},${g},${b})`;
}

interface USMapProps {
  regions: RegionMetrics[];
  metric: "avg_ai_score" | "avg_expert_score" | "avg_user_score";
  selectedRegion: string | null;
  onSelectRegion: (region: string | null) => void;
}

interface TooltipData {
  name: string;
  abbr: string;
  count: number;
  avg_ai_score: number | null;
  avg_expert_score: number | null;
  avg_user_score: number | null;
  x: number;
  y: number;
}

function USMapInner({ regions, metric, selectedRegion, onSelectRegion }: USMapProps) {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  const regionMap = new Map(regions.map((r) => [r.region, r]));
  const scores = regions.map((r) => r[metric]).filter((s): s is number => s !== null);
  const maxScore = scores.length > 0 ? Math.max(...scores) : 100;

  const handleMouseMove = useCallback((stateName: string, abbr: string, e: React.MouseEvent) => {
    const data = regionMap.get(abbr);
    setTooltip({
      name: stateName,
      abbr,
      count: data?.count ?? 0,
      avg_ai_score: data?.avg_ai_score ?? null,
      avg_expert_score: data?.avg_expert_score ?? null,
      avg_user_score: data?.avg_user_score ?? null,
      x: e.clientX,
      y: e.clientY,
    });
  }, [regionMap]);

  const handleMouseLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  return (
    <div className="relative">
      <ComposableMap projection="geoAlbersUsa" width={900} height={500}>
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const stateName = geo.properties.name;
              const abbr = STATE_ABBR[stateName];
              const data = abbr ? regionMap.get(abbr) : undefined;
              const score = data ? data[metric] : null;
              const isSelected = abbr === selectedRegion;

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  onClick={() => {
                    if (abbr) onSelectRegion(isSelected ? null : abbr);
                  }}
                  onMouseMove={(e: React.MouseEvent) => {
                    if (abbr) handleMouseMove(stateName, abbr, e);
                  }}
                  onMouseLeave={handleMouseLeave}
                  style={{
                    default: {
                      fill: isSelected ? "#B8553A" : scoreToColor(score, maxScore),
                      stroke: "#FFFFFF",
                      strokeWidth: 0.75,
                      outline: "none",
                    },
                    hover: {
                      fill: isSelected ? "#9C4530" : data ? "#D4A373" : "#DAD8D5",
                      stroke: "#FFFFFF",
                      strokeWidth: 1,
                      outline: "none",
                      cursor: data ? "pointer" : "default",
                    },
                    pressed: {
                      fill: "#9C4530",
                      stroke: "#FFFFFF",
                      strokeWidth: 1,
                      outline: "none",
                    },
                  }}
                />
              );
            })
          }
        </Geographies>
      </ComposableMap>

      {/* Hover tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 pointer-events-none rounded border border-border bg-surface px-3 py-2 shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y - 12 }}
        >
          <p className="text-sm font-medium text-text-primary">{tooltip.name}</p>
          {tooltip.count > 0 ? (
            <>
              <p className="text-xs text-text-secondary mt-0.5">
                {tooltip.count} startup{tooltip.count !== 1 ? "s" : ""}
              </p>
              <div className="grid grid-cols-3 gap-3 mt-1.5 text-xs">
                <div>
                  <span className="text-text-tertiary">AI</span>
                  <span className="ml-1 tabular-nums text-text-primary">
                    {tooltip.avg_ai_score?.toFixed(1) ?? "—"}
                  </span>
                </div>
                <div>
                  <span className="text-text-tertiary">Contrib</span>
                  <span className="ml-1 tabular-nums text-text-primary">
                    {tooltip.avg_expert_score?.toFixed(1) ?? "—"}
                  </span>
                </div>
                <div>
                  <span className="text-text-tertiary">Comm</span>
                  <span className="ml-1 tabular-nums text-text-primary">
                    {tooltip.avg_user_score?.toFixed(1) ?? "—"}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-xs text-text-tertiary mt-0.5">No data</p>
          )}
        </div>
      )}
    </div>
  );
}

export const USMap = memo(USMapInner);
