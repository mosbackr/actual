interface ReviewCardProps {
  variant: "expert" | "user";
  reviewer: { name: string; credentials?: string };
  score: number;
  comment: string;
  date: string;
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-score-high";
  if (score >= 40) return "text-score-mid";
  return "text-score-low";
}

export function ReviewCard({ variant, reviewer, score, comment, date }: ReviewCardProps) {
  return (
    <div className="rounded border border-border bg-surface p-6">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-text-primary">{reviewer.name}</span>
            <span className="text-xs px-2 py-0.5 rounded border border-border text-text-tertiary">
              {variant === "expert" ? "Expert" : "Community"}
            </span>
          </div>
          {reviewer.credentials && (
            <p className="text-xs text-text-tertiary mt-0.5">{reviewer.credentials}</p>
          )}
        </div>
        <div className="text-right">
          <div className={`font-serif text-xl tabular-nums ${scoreColor(score)}`}>{Math.round(score)}</div>
          <div className="text-xs text-text-tertiary">{new Date(date).toLocaleDateString()}</div>
        </div>
      </div>
      <p className="text-sm text-text-secondary">{comment}</p>
    </div>
  );
}
