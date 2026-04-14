"use client";

import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  ScatterChart, Scatter, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import type { AnalystChartConfig } from "@/lib/types";

const DEFAULT_COLORS = [
  "#6366f1", "#f59e0b", "#10b981", "#ef4444",
  "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16",
];

export function AnalystChart({ config }: { config: AnalystChartConfig }) {
  const { type, title, data, colors } = config;
  const palette = colors || DEFAULT_COLORS;
  const xKey = config.xKey || config.nameKey || "name";
  const yKeys = config.yKeys || (config.dataKey ? [config.dataKey] : ["value"]);

  if (!data || data.length === 0) return null;

  return (
    <div className="my-4 rounded border border-border bg-surface-alt p-4">
      {title && <p className="text-xs font-medium text-text-secondary mb-3">{title}</p>}
      <ResponsiveContainer width="100%" height={300}>
        {type === "pie" ? (
          <PieChart>
            <Pie
              data={data}
              dataKey={yKeys[0]}
              nameKey={xKey}
              cx="50%"
              cy="50%"
              outerRadius={100}
              label={({ name, percent }: { name: string; percent: number }) =>
                `${name} ${(percent * 100).toFixed(0)}%`
              }
            >
              {data.map((_, i) => (
                <Cell key={i} fill={palette[i % palette.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        ) : type === "scatter" ? (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Scatter key={yk} name={yk} data={data} fill={palette[i % palette.length]} />
            ))}
            <Legend />
          </ScatterChart>
        ) : type === "area" ? (
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Area
                key={yk}
                type="monotone"
                dataKey={yk}
                fill={palette[i % palette.length]}
                fillOpacity={0.3}
                stroke={palette[i % palette.length]}
              />
            ))}
            <Legend />
          </AreaChart>
        ) : type === "line" ? (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Line
                key={yk}
                type="monotone"
                dataKey={yk}
                stroke={palette[i % palette.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
            <Legend />
          </LineChart>
        ) : (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Bar key={yk} dataKey={yk} fill={palette[i % palette.length]} radius={[4, 4, 0, 0]} />
            ))}
            <Legend />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
