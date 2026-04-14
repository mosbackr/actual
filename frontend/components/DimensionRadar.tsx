"use client";

import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Legend, ResponsiveContainer,
} from "recharts";
import type { ScoreHistory } from "@/lib/types";

interface DimensionRadarProps {
  history: ScoreHistory[];
}

export function DimensionRadar({ history }: DimensionRadarProps) {
  const latest: Record<string, Record<string, number>> = {};
  for (const entry of history) {
    if (entry.dimensions_json) {
      latest[entry.score_type] = entry.dimensions_json;
    }
  }

  const allDimensions = new Set<string>();
  for (const dims of Object.values(latest)) {
    for (const key of Object.keys(dims)) {
      allDimensions.add(key);
    }
  }

  if (allDimensions.size === 0) {
    return <div className="text-center py-8 text-text-tertiary text-sm">No dimension breakdown available yet</div>;
  }

  const data = Array.from(allDimensions).map((dim) => ({
    dimension: dim.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    ai: latest["ai"]?.[dim] ?? 0,
    expert: latest["expert_aggregate"]?.[dim] ?? 0,
    community: latest["user_aggregate"]?.[dim] ?? 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={350}>
      <RadarChart data={data}>
        <PolarGrid stroke="#E8E6E3" />
        <PolarAngleAxis dataKey="dimension" stroke="#6B6B6B" fontSize={11} />
        <PolarRadiusAxis domain={[0, 100]} stroke="#E8E6E3" fontSize={10} />
        <Radar name="AI" dataKey="ai" stroke="#F28C28" fill="#F28C28" fillOpacity={0.1} />
        <Radar name="Contributor" dataKey="expert" stroke="#2D6A4F" fill="#2D6A4F" fillOpacity={0.1} />
        <Radar name="Community" dataKey="community" stroke="#B8860B" fill="#B8860B" fillOpacity={0.1} />
        <Legend />
      </RadarChart>
    </ResponsiveContainer>
  );
}
