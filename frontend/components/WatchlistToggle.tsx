"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";

interface WatchlistToggleProps {
  startupId: string;
  initialWatched: boolean;
  size?: "sm" | "md";
  onToggle?: (watched: boolean) => void;
}

export function WatchlistToggle({ startupId, initialWatched, size = "sm", onToggle }: WatchlistToggleProps) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [watched, setWatched] = useState(initialWatched);
  const [loading, setLoading] = useState(false);

  if (!token) return null;

  const iconSize = size === "md" ? "w-5 h-5" : "w-4 h-4";

  async function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (loading) return;
    setLoading(true);
    const newState = !watched;
    setWatched(newState); // optimistic

    try {
      if (newState) {
        await api.addToWatchlist(token, startupId);
      } else {
        await api.removeFromWatchlist(token, startupId);
      }
      onToggle?.(newState);
    } catch {
      setWatched(!newState); // revert
    }
    setLoading(false);
  }

  return (
    <button
      onClick={toggle}
      className={`p-1 transition ${watched ? "text-accent" : "text-text-tertiary hover:text-accent/70"}`}
      aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
      title={watched ? "Remove from watchlist" : "Add to watchlist"}
    >
      <svg
        className={iconSize}
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
