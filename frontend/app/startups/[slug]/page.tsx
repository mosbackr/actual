import { notFound } from "next/navigation";
import type { StartupDetail } from "@/lib/types";
import { ScoreComparison } from "@/components/ScoreComparison";
import { ScoreTimeline } from "@/components/ScoreTimeline";
import { DimensionRadar } from "@/components/DimensionRadar";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
};

async function getStartup(slug: string): Promise<StartupDetail | null> {
  const res = await fetch(`${API_URL}/api/startups/${slug}`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

export default async function StartupPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const startup = await getStartup(slug);
  if (!startup) notFound();

  return (
    <div className="max-w-4xl mx-auto">
      {/* Hero */}
      <div className="flex items-start gap-6 mb-8">
        {startup.logo_url ? (
          <img src={startup.logo_url} alt={startup.name} className="h-20 w-20 rounded-xl object-cover" />
        ) : (
          <div className="h-20 w-20 rounded-xl bg-gray-800 flex items-center justify-center text-2xl font-bold text-gray-500">
            {startup.name[0]}
          </div>
        )}
        <div className="flex-1">
          <h1 className="text-3xl font-bold">{startup.name}</h1>
          <p className="text-gray-400 mt-2">{startup.description}</p>
          <div className="flex flex-wrap gap-2 mt-3">
            <span className="rounded-full bg-indigo-900/40 px-3 py-1 text-xs font-medium text-indigo-300 border border-indigo-800">
              {stageLabels[startup.stage] || startup.stage}
            </span>
            {startup.industries.map((ind) => (
              <span key={ind.id} className="rounded-full bg-gray-800 px-3 py-1 text-xs text-gray-400">{ind.name}</span>
            ))}
            {startup.website_url && (
              <a href={startup.website_url} target="_blank" rel="noopener noreferrer"
                className="rounded-full bg-gray-800 px-3 py-1 text-xs text-indigo-400 hover:text-indigo-300">
                Visit Website &rarr;
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Scores Overview */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-4">Scores Overview</h2>
        <ScoreComparison aiScore={startup.ai_score} expertScore={startup.expert_score} userScore={startup.user_score} />
      </section>

      {/* Score Timeline */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-4">Score History</h2>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <ScoreTimeline history={startup.score_history} />
        </div>
      </section>

      {/* Dimension Breakdown */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-4">Dimension Breakdown</h2>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <DimensionRadar history={startup.score_history} />
        </div>
      </section>

      {/* Media */}
      {startup.media.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4">Media Coverage</h2>
          <div className="space-y-3">
            {startup.media.map((m) => (
              <a key={m.id} href={m.url} target="_blank" rel="noopener noreferrer"
                className="block rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-white">{m.title}</p>
                    <p className="text-xs text-gray-500 mt-1">{m.source} &middot; {m.media_type.replace("_", " ")}</p>
                  </div>
                  {m.published_at && (
                    <span className="text-xs text-gray-500">{new Date(m.published_at).toLocaleDateString()}</span>
                  )}
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

      {/* Reviews placeholder */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-4">Expert Reviews</h2>
        <p className="text-gray-500 text-sm">No expert reviews yet.</p>
      </section>
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-4">Community Reviews</h2>
        <p className="text-gray-500 text-sm">No community reviews yet.</p>
      </section>
    </div>
  );
}
