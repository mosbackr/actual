import { ScoreBadge } from "./ScoreBadge";

interface ScoreComparisonProps {
  aiScore: number | null;
  expertScore: number | null;
  userScore: number | null;
}

export function ScoreComparison({ aiScore, expertScore, userScore }: ScoreComparisonProps) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <ScoreBadge label="AI" score={aiScore} />
      <ScoreBadge label="Expert" score={expertScore} />
      <ScoreBadge label="Community" score={userScore} />
    </div>
  );
}
