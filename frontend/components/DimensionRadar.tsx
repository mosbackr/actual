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
    return <div className="text-center py-8 text-gray-500 text-sm">No dimension breakdown available yet</div>;
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
        <PolarGrid stroke="#374151" />
        <PolarAngleAxis dataKey="dimension" stroke="#9CA3AF" fontSize={11} />
        <PolarRadiusAxis domain={[0, 100]} stroke="#4B5563" fontSize={10} />
        <Radar name="AI" dataKey="ai" stroke="#818CF8" fill="#818CF8" fillOpacity={0.15} />
        <Radar name="Expert" dataKey="expert" stroke="#34D399" fill="#34D399" fillOpacity={0.15} />
        <Radar name="Community" dataKey="community" stroke="#FBBF24" fill="#FBBF24" fillOpacity={0.15} />
        <Legend />
      </RadarChart>
    </ResponsiveContainer>
  );
}
