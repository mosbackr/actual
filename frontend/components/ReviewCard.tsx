interface ReviewCardProps {
  variant: "expert" | "user";
  reviewer: { name: string; credentials?: string };
  score: number;
  comment: string;
  date: string;
}

export function ReviewCard({ variant, reviewer, score, comment, date }: ReviewCardProps) {
  const borderColor = variant === "expert" ? "border-emerald-800" : "border-gray-700";
  const badgeColor = variant === "expert" ? "bg-emerald-900/50 text-emerald-400" : "bg-gray-800 text-gray-400";

  return (
    <div className={`rounded-lg border ${borderColor} bg-gray-900 p-4`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-white">{reviewer.name}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${badgeColor}`}>
              {variant === "expert" ? "Expert" : "Community"}
            </span>
          </div>
          {reviewer.credentials && (
            <p className="text-xs text-gray-500 mt-0.5">{reviewer.credentials}</p>
          )}
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-white">{Math.round(score)}</div>
          <div className="text-xs text-gray-500">{new Date(date).toLocaleDateString()}</div>
        </div>
      </div>
      <p className="text-sm text-gray-300">{comment}</p>
    </div>
  );
}
