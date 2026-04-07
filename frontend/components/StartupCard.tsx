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
};

interface StartupCardProps {
  startup: StartupCardType;
}

export function StartupCard({ startup }: StartupCardProps) {
  return (
    <Link href={`/startups/${startup.slug}`}>
      <div className="group rounded-xl border border-gray-800 bg-gray-900 p-5 hover:border-gray-600 transition-all hover:shadow-lg hover:shadow-indigo-900/10">
        <div className="flex items-start gap-4 mb-4">
          {startup.logo_url ? (
            <img
              src={startup.logo_url}
              alt={startup.name}
              className="h-12 w-12 rounded-lg object-cover"
            />
          ) : (
            <div className="h-12 w-12 rounded-lg bg-gray-800 flex items-center justify-center text-lg font-bold text-gray-500">
              {startup.name[0]}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-white group-hover:text-indigo-400 transition truncate">
              {startup.name}
            </h3>
            <p className="text-sm text-gray-400 line-clamp-2 mt-1">
              {startup.description}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <span className="inline-block rounded-full bg-indigo-900/40 px-2.5 py-0.5 text-xs font-medium text-indigo-300 border border-indigo-800">
            {stageLabels[startup.stage] || startup.stage}
          </span>
          {startup.industries.map((ind) => (
            <span
              key={ind.id}
              className="inline-block rounded-full bg-gray-800 px-2.5 py-0.5 text-xs text-gray-400"
            >
              {ind.name}
            </span>
          ))}
        </div>

        <ScoreComparison
          aiScore={startup.ai_score}
          expertScore={startup.expert_score}
          userScore={startup.user_score}
        />
      </div>
    </Link>
  );
}
