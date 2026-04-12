function scoreColor(score: number | null): string {
  if (score === null) return "text-text-tertiary";
  if (score >= 70) return "text-score-high";
  if (score >= 40) return "text-score-mid";
  return "text-score-low";
}

interface ScoreBadgeProps {
  label: string;
  score: number | null;
}

export function ScoreBadge({ label, score }: ScoreBadgeProps) {
  return (
    <div className="text-center">
      <div className="text-xs uppercase tracking-wider text-text-tertiary font-medium mb-1">{label}</div>
      <div className={`font-serif text-2xl tabular-nums ${scoreColor(score)}`}>
        {score !== null ? Math.round(score) : "\u2014"}
      </div>
    </div>
  );
}
