"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export function AuthButton() {
  const { data: session } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  if (session) {
    const initials = (session.user?.name || "?")
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);

    return (
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 hover:opacity-80 transition"
        >
          {session.user?.image ? (
            <img src={session.user.image} alt="" className="h-7 w-7 rounded-full object-cover" />
          ) : (
            <div className="h-7 w-7 rounded-full bg-accent/10 flex items-center justify-center text-accent text-xs font-medium">
              {initials}
            </div>
          )}
          <span className="text-sm text-text-secondary">{session.user?.name}</span>
          <svg
            className={`w-3.5 h-3.5 text-text-tertiary transition-transform ${open ? "rotate-180" : ""}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {open && (
          <div className="absolute right-0 top-full mt-2 w-44 rounded border border-border bg-surface shadow-lg py-1 z-50">
            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-alt transition"
            >
              Profile
            </Link>
            <Link
              href="/billing"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-alt transition"
            >
              Billing
            </Link>
            <Link
              href="/experts/apply"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-alt transition"
            >
              Contribute
            </Link>
            <div className="border-t border-border my-1" />
            <button
              onClick={() => {
                setOpen(false);
                signOut({ callbackUrl: "/" });
              }}
              className="block w-full text-left px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-alt transition"
            >
              Sign Out
            </button>
          </div>
        )}
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
