import Link from "next/link";
import type { StartupCard as StartupCardType } from "@/lib/types";
import { ScoreComparison } from "./ScoreComparison";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
  public: "Public",
};

interface StartupCardProps {
  startup: StartupCardType;
}

export function StartupCard({ startup }: StartupCardProps) {
  return (
    <Link href={`/startups/${startup.slug}`}>
      <div className="group rounded border border-border bg-surface p-6 hover:border-text-tertiary transition-colors">
        <div className="flex items-start gap-4 mb-4">
          {startup.logo_url ? (
            <img
              src={startup.logo_url}
              alt={startup.name}
              className="h-12 w-12 rounded object-cover"
            />
          ) : (
            <div className="h-12 w-12 rounded bg-background flex items-center justify-center font-serif text-lg text-text-tertiary">
              {startup.name[0]}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="font-serif text-lg text-text-primary group-hover:text-accent transition truncate">
              {startup.name}
            </h3>
            <p className="text-sm text-text-secondary line-clamp-2 mt-1">
              {startup.description}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <span className="inline-block rounded border border-border px-2.5 py-0.5 text-xs font-medium text-text-secondary">
            {stageLabels[startup.stage] || startup.stage}
          </span>
          {startup.industries.map((ind) => (
            <span
              key={ind.id}
              className="inline-block rounded px-2.5 py-0.5 text-xs text-text-tertiary"
            >
              {ind.name}
            </span>
          ))}
        </div>

        <div className="pt-4 border-t border-border">
          <ScoreComparison
            aiScore={startup.ai_score}
            expertScore={startup.expert_score}
            userScore={startup.user_score}
          />
        </div>
      </div>
    </Link>
  );
}
