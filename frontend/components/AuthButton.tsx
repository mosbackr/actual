"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import Link from "next/link";

export function AuthButton() {
  const { data: session } = useSession();

  if (session) {
    const initials = (session.user?.name || "?")
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);

    return (
      <div className="flex items-center gap-3">
        <Link href="/profile" className="flex items-center gap-2 hover:opacity-80 transition">
          {session.user?.image ? (
            <img src={session.user.image} alt="" className="h-7 w-7 rounded-full object-cover" />
          ) : (
            <div className="h-7 w-7 rounded-full bg-accent/10 flex items-center justify-center text-accent text-xs font-medium">
              {initials}
            </div>
          )}
          <span className="text-sm text-text-secondary">{session.user?.name}</span>
        </Link>
        <button
          onClick={() => signOut({ callbackUrl: "/" })}
          className="text-sm px-3 py-1.5 rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Link
        href="/auth/signin"
        className="text-sm px-3 py-1.5 rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
      >
        Sign In
      </Link>
      <Link
        href="/auth/signup"
        className="text-sm px-3 py-1.5 rounded bg-accent text-white hover:bg-accent-hover transition"
      >
        Sign Up
      </Link>
    </div>
  );
}
