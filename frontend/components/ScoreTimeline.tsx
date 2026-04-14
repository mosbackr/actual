"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import type { ScoreHistory } from "@/lib/types";

interface ScoreTimelineProps {
  history: ScoreHistory[];
}

export function ScoreTimeline({ history }: ScoreTimelineProps) {
  const dateMap = new Map<string, Record<string, number>>();
  for (const entry of history) {
    const date = new Date(entry.recorded_at).toLocaleDateString();
    const existing = dateMap.get(date) || {};
    existing[entry.score_type] = entry.score_value;
    dateMap.set(date, existing);
  }

  const data = Array.from(dateMap.entries()).map(([date, scores]) => ({ date, ...scores }));

  if (data.length === 0) {
    return <div className="text-center py-8 text-text-tertiary text-sm">No scoring history yet</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" />
        <XAxis dataKey="date" stroke="#9B9B9B" fontSize={12} />
        <YAxis domain={[0, 100]} stroke="#9B9B9B" fontSize={12} />
        <Tooltip contentStyle={{ backgroundColor: "#FFFFFF", border: "1px solid #E8E6E3", borderRadius: "4px", color: "#1A1A1A" }} />
        <Legend />
        <Line type="monotone" dataKey="ai" name="AI Score" stroke="#F28C28" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="expert_aggregate" name="Contributor Score" stroke="#2D6A4F" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="user_aggregate" name="Community Score" stroke="#B8860B" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
