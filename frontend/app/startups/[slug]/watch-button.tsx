"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";

export function WatchButton({ startupId }: { startupId: string }) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [watched, setWatched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!token) return;
    api.getWatchlistIds(token).then((data) => {
      setWatched(data.ids.includes(startupId));
      setReady(true);
    }).catch(() => setReady(true));
  }, [token, startupId]);

  if (!token || !ready) return null;

  async function toggle() {
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
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded border text-xs font-medium transition ${
        watched
          ? "border-accent text-accent bg-accent/5"
          : "border-border text-text-secondary hover:border-accent/50 hover:text-accent"
      }`}
    >
      <svg
        className="w-3.5 h-3.5"
        viewBox="0 0 24 24"
        fill={watched ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
      </svg>
      {watched ? "Watching" : "Watch"}
    </button>
  );
}
