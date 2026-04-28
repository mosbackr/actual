"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
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

function NavIcon({
  href,
  label,
  active,
  children,
}: {
  href: string;
  label: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`group relative p-2 rounded-lg transition ${
        active
          ? "text-accent bg-accent/8"
          : "text-text-secondary hover:text-text-primary hover:bg-surface-alt"
      }`}
    >
      {children}
      <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-full mt-2 px-2 py-1 rounded bg-text-primary text-surface text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50">
        {label}
      </span>
    </Link>
  );
}

export function Navbar() {
  const { data: session } = useSession();
  const pathname = usePathname();
  const [score, setScore] = useState<{ overall_score: number; investor_id: string } | null>(null);
  const [zoomConnected, setZoomConnected] = useState<boolean | null>(null);

  useEffect(() => {
    if (!session) return;
    const token = (session as any)?.backendToken;
    if (!token) return;

    api.getZoomConnection(token).then((data) => {
      setZoomConnected(data.connected);
    }).catch(() => {});

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
        <div className="flex h-14 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2 font-serif text-xl text-text-primary">
              <LogoIcon size={24} />
              <span className="hidden sm:inline">Deep Thesis</span>
            </Link>
            {session && (
              <div className="hidden md:flex items-center gap-1">
                {/* Companies */}
                <NavIcon href="/startups" label="Companies" active={pathname.startsWith("/startups")}>
                  <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="7" height="9" rx="1" />
                    <rect x="14" y="3" width="7" height="5" rx="1" />
                    <rect x="14" y="12" width="7" height="9" rx="1" />
                    <rect x="3" y="16" width="7" height="5" rx="1" />
                  </svg>
                </NavIcon>
                {/* Analyze */}
                <NavIcon href="/analyze" label="Analyze" active={pathname.startsWith("/analyze")}>
                  <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="11" cy="11" r="7" />
                    <path d="M21 21l-4.35-4.35" />
                    <path d="M8 11h6M11 8v6" />
                  </svg>
                </NavIcon>
                {/* Insights */}
                <NavIcon href="/insights" label="Insights" active={pathname.startsWith("/insights")}>
                  <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18h6M10 22h4" />
                    <path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" />
                  </svg>
                </NavIcon>
                {/* Pitch Intel */}
                <NavIcon href="/pitch-intelligence" label="Pitch Intel" active={pathname.startsWith("/pitch-intelligence")}>
                  <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2v1M12 21v1M4.22 4.22l.7.7M18.36 18.36l.7.7M1 12h1M21 12h1M4.22 19.78l.7-.7M18.36 5.64l.7-.7" />
                    <circle cx="12" cy="12" r="5" />
                  </svg>
                </NavIcon>
                {/* Datarooms */}
                <NavIcon href="/datarooms" label="Datarooms" active={pathname.startsWith("/datarooms") || pathname.startsWith("/dataroom/")}>
                  <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    <line x1="12" y1="11" x2="12" y2="17" />
                    <line x1="9" y1="14" x2="15" y2="14" />
                  </svg>
                </NavIcon>
              </div>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {score && (
              <Link
                href={`/score/${score.investor_id}#portfolio`}
                className="group relative p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-alt transition hidden md:flex"
              >
                <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="7" width="6" height="15" rx="1" />
                  <rect x="9" y="3" width="6" height="19" rx="1" />
                  <rect x="16" y="11" width="6" height="11" rx="1" />
                </svg>
                <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-full mt-2 px-2 py-1 rounded bg-text-primary text-surface text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50">
                  Portfolio
                </span>
              </Link>
            )}
            {score && (
              <Link
                href={`/score/${score.investor_id}`}
                className={`hidden md:flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium transition hover:opacity-80 ${scorePillClasses(score.overall_score)}`}
              >
                <span className="tabular-nums">{Math.round(score.overall_score)}</span>
              </Link>
            )}
            {session && zoomConnected === false && (
              <Link
                href="/integrations/zoom"
                className="group relative p-2 rounded-lg text-blue-500 hover:bg-blue-50 transition hidden md:flex"
              >
                <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
                </svg>
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-full mt-2 px-2 py-1 rounded bg-text-primary text-surface text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50">
                  Connect Zoom
                </span>
              </Link>
            )}
            {session && zoomConnected === true && (
              <Link
                href="/integrations/zoom"
                className="group relative p-2 rounded-lg text-green-600 hover:bg-green-50 transition hidden md:flex"
              >
                <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
                </svg>
                <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-full mt-2 px-2 py-1 rounded bg-text-primary text-surface text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50">
                  Zoom Connected
                </span>
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
