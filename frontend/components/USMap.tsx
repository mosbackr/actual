"use client";

import { memo } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  ZoomableGroup,
} from "react-simple-maps";
import type { RegionMetrics } from "@/lib/types";

const GEO_URL = "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";

// Map state FIPS names to our location_state values
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

function scoreToColor(score: number | null, max: number): string {
  if (score === null || max === 0) return "#E8E6E3";
  const t = Math.min(score / max, 1);
  // Interpolate from light warm gray to accent (terracotta)
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

function USMapInner({ regions, metric, selectedRegion, onSelectRegion }: USMapProps) {
  const regionMap = new Map(regions.map((r) => [r.region, r]));
  const scores = regions.map((r) => r[metric]).filter((s): s is number => s !== null);
  const maxScore = scores.length > 0 ? Math.max(...scores) : 100;

  return (
    <ComposableMap projection="geoAlbersUsa" width={900} height={500}>
      <ZoomableGroup>
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
                  style={{
                    default: {
                      fill: isSelected ? "#B8553A" : scoreToColor(score, maxScore),
                      stroke: "#FFFFFF",
                      strokeWidth: 0.75,
                      outline: "none",
                    },
                    hover: {
                      fill: isSelected ? "#9C4530" : "#D4A373",
                      stroke: "#FFFFFF",
                      strokeWidth: 1,
                      outline: "none",
                      cursor: "pointer",
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
      </ZoomableGroup>
    </ComposableMap>
  );
}

export const USMap = memo(USMapInner);
