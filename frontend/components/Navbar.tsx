"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { AuthButton } from "./AuthButton";
import { NotificationBell } from "./NotificationBell";
import { WatchlistIcon } from "./WatchlistIcon";
import { LogoIcon } from "./LogoIcon";
import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

function scorePillClasses(score: number): string {
  if (score >= 80) return "border-[#2D6A4F] text-[#2D6A4F] bg-[#2D6A4F]/5";
  if (score >= 60) return "border-[#B8860B] text-[#B8860B] bg-[#B8860B]/5";
  if (score >= 40) return "border-[#6B6B6B] text-[#6B6B6B] bg-[#6B6B6B]/5";
  return "border-[#A23B3B] text-[#A23B3B] bg-[#A23B3B]/5";
}

export function Navbar() {
  const { data: session } = useSession();
  const [score, setScore] = useState<{ overall_score: number; investor_id: string } | null>(null);
  const [zoomConnected, setZoomConnected] = useState<boolean | null>(null);

  useEffect(() => {
    if (!session) return;
    const token = (session as any)?.backendToken;
    if (!token) return;

    // Fetch Zoom connection status
    api.getZoomConnection(token).then((data) => {
      setZoomConnected(data.connected);
    }).catch(() => {});

    // Fetch investor score
    if ((session as any).role !== "investor") return;
    fetch(`${API_URL}/api/investors/me/ranking`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed");
        return res.json();
      })
      .then((data) => {
        setScore({ overall_score: data.overall_score, investor_id: data.investor_id });
      })
      .catch(() => {});
  }, [session]);

  return (
    <nav className="border-b border-border bg-surface">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-2 font-serif text-xl text-text-primary">
              <LogoIcon size={28} />
              Deep Thesis
            </Link>
            {session && (
              <div className="hidden md:flex items-center gap-6">
                <Link href="/startups" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Companies
                </Link>
                <Link href="/analyze" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Analyze
                </Link>
                <Link href="/insights" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Insights
                </Link>
                <Link href="/pitch-intelligence" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Pitch Intel
                </Link>
                <Link
                  href="/experts/apply"
                  className="text-sm px-3 py-1 rounded border border-accent text-accent hover:bg-accent/5 transition"
                >
                  Contribute
                </Link>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {score && (
              <Link
                href={`/score/${score.investor_id}#portfolio`}
                className="hidden md:flex text-sm text-text-secondary hover:text-text-primary transition"
              >
                Portfolio
              </Link>
            )}
            {score && (
              <Link
                href={`/score/${score.investor_id}`}
                className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition hover:opacity-80 ${scorePillClasses(score.overall_score)}`}
              >
                <span>Score</span>
                <span className="tabular-nums">{Math.round(score.overall_score)}</span>
              </Link>
            )}
            {session && zoomConnected === false && (
              <Link
                href="/integrations/zoom"
                className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded border border-blue-400 text-xs font-medium text-blue-500 hover:bg-blue-50 transition"
                title="Connect Zoom to import recordings"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
                </svg>
                Connect Zoom
              </Link>
            )}
            {session && zoomConnected === true && (
              <Link
                href="/integrations/zoom"
                className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded border border-green-400 text-xs font-medium text-green-600 hover:bg-green-50 transition"
                title="Zoom connected"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
                </svg>
                Zoom Connected
              </Link>
            )}
            {session && <WatchlistIcon />}
            {session && <NotificationBell />}
            <AuthButton />
          </div>
        </div>
      </div>
    </nav>
  );
}
