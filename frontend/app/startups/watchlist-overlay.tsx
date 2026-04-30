"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";

const WatchedIdsContext = createContext<Set<string>>(new Set());

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [watchedIds, setWatchedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!token) return;
    api.getWatchlistIds(token).then((data) => {
      setWatchedIds(new Set(data.ids));
    }).catch(() => {});
  }, [token]);

  return (
    <WatchedIdsContext.Provider value={watchedIds}>
      {children}
    </WatchedIdsContext.Provider>
  );
}

export function CardBookmark({ startupId }: { startupId: string }) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const watchedIds = useContext(WatchedIdsContext);
  const [watched, setWatched] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setWatched(watchedIds.has(startupId));
  }, [watchedIds, startupId]);

  if (!token) return null;

  async function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (loading) return;
    setLoading(true);
    const newState = !watched;
    setWatched(newState);

    try {
      if (newState) {
        await api.addToWatchlist(token, startupId);
      } else {
        await api.removeFromWatchlist(token, startupId);
      }
    } catch {
      setWatched(!newState);
    }
    setLoading(false);
  }

  return (
    <button
      onClick={toggle}
      className={`p-1 transition ${watched ? "text-accent" : "text-text-tertiary hover:text-accent/70"}`}
      aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
    >
      <svg
        className="w-4 h-4"
        viewBox="0 0 24 24"
        fill={watched ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
      </svg>
    </button>
  );
}
