"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { WatchlistEntry } from "@/lib/types";
import { WatchlistToggle } from "@/components/WatchlistToggle";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
  public: "Public",
};

export default function WatchlistPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);

  const loadWatchlist = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getWatchlist(token, page);
      setEntries(data.items);
      setTotalPages(data.pages);
      setTotal(data.total);
    } catch {
      // silent
    }
    setLoading(false);
  }, [token, page]);

  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  function handleRemove(startupId: string, watched: boolean) {
    if (!watched) {
      setEntries((prev) => prev.filter((e) => e.startup_id !== startupId));
      setTotal((prev) => prev - 1);
    }
  }

  if (!session) {
    return (
      <div className="text-center py-20 text-text-tertiary text-sm">
        <p>Sign in to use your watchlist.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-serif text-3xl text-text-primary">Watchlist</h1>
        <p className="text-text-secondary text-sm mt-2">
          {total} {total === 1 ? "company" : "companies"} saved
        </p>
      </div>

      {loading ? (
        <p className="text-text-tertiary text-sm py-10 text-center">Loading...</p>
      ) : entries.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-text-tertiary text-sm mb-4">No startups in your watchlist yet.</p>
          <Link
            href="/startups"
            className="px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            Browse Companies
          </Link>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {entries.map((entry) => {
              const startup = entry.startup;
              return (
                <div key={startup.id} className="relative rounded border border-border bg-surface p-5 hover:border-text-tertiary transition">
                  <div className="absolute top-3 right-3">
                    <WatchlistToggle
                      startupId={startup.id}
                      initialWatched={true}
                      onToggle={(watched) => handleRemove(startup.id, watched)}
                    />
                  </div>
                  <Link href={`/startups/${startup.slug}`} className="block">
                    <div className="flex items-center gap-3 mb-3">
                      {startup.logo_url ? (
                        <img src={startup.logo_url} alt={startup.name} className="h-10 w-10 rounded object-cover" />
                      ) : (
                        <div className="h-10 w-10 rounded bg-background border border-border flex items-center justify-center font-serif text-lg text-text-tertiary">
                          {startup.name[0]}
                        </div>
                      )}
                      <div className="min-w-0 pr-6">
                        <h3 className="text-sm font-medium text-text-primary truncate">{startup.name}</h3>
                        {startup.tagline && (
                          <p className="text-xs text-text-tertiary truncate">{startup.tagline}</p>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-text-secondary line-clamp-2 mb-3">{startup.description}</p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs px-2 py-0.5 rounded border border-border text-text-tertiary">
                        {stageLabels[startup.stage] || startup.stage}
                      </span>
                      {startup.industries.length > 0 && (
                        <span className="text-xs text-text-tertiary">
                          {startup.industries[0].name}
                        </span>
                      )}
                      {startup.ai_score != null && (
                        <span className={`text-xs font-medium tabular-nums ml-auto ${
                          startup.ai_score >= 70 ? "text-score-high" : startup.ai_score >= 40 ? "text-score-mid" : "text-score-low"
                        }`}>
                          AI: {startup.ai_score.toFixed(0)}
                        </span>
                      )}
                    </div>
                  </Link>
                </div>
              );
            })}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-10">
              {page > 1 && (
                <button
                  onClick={() => setPage(page - 1)}
                  className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                >
                  Previous
                </button>
              )}
              <span className="text-sm text-text-tertiary px-3">
                Page {page} of {totalPages}
              </span>
              {page < totalPages && (
                <button
                  onClick={() => setPage(page + 1)}
                  className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                >
                  Next
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
