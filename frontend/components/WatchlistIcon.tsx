"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export function WatchlistIcon() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();
  const [count, setCount] = useState(0);

  const loadCount = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getWatchlistIds(token);
      setCount(data.ids.length);
    } catch {
      // silent
    }
  }, [token]);

  useEffect(() => {
    loadCount();
  }, [loadCount]);

  return (
    <button
      onClick={() => router.push("/watchlist")}
      className="relative p-1.5 text-text-secondary hover:text-text-primary transition"
      aria-label="Watchlist"
    >
      <svg
        className="w-5 h-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
      </svg>
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 flex items-center justify-center rounded-full bg-accent text-white text-[10px] font-medium px-1">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </button>
  );
}
