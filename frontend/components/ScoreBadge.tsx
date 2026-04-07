function scoreColor(score: number | null): string {
  if (score === null) return "bg-gray-700 text-gray-400";
  if (score >= 70) return "bg-emerald-900/50 text-emerald-400 border border-emerald-700";
  if (score >= 40) return "bg-yellow-900/50 text-yellow-400 border border-yellow-700";
  return "bg-red-900/50 text-red-400 border border-red-700";
}

interface ScoreBadgeProps {
  label: string;
  score: number | null;
}

export function ScoreBadge({ label, score }: ScoreBadgeProps) {
  return (
    <div className={`rounded-lg px-3 py-2 text-center ${scoreColor(score)}`}>
      <div className="text-xs uppercase tracking-wide opacity-70">{label}</div>
      <div className="text-lg font-bold">
        {score !== null ? Math.round(score) : "—"}
      </div>
    </div>
  );
}
