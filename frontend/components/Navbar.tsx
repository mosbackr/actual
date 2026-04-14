"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { AuthButton } from "./AuthButton";
import { NotificationBell } from "./NotificationBell";
import { LogoIcon } from "./LogoIcon";

export function Navbar() {
  const { data: session } = useSession();

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
            {session && <NotificationBell />}
            <AuthButton />
          </div>
        </div>
      </div>
    </nav>
  );
}
