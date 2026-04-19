"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import { LogoIcon } from "./LogoIcon";

const NAV_ITEMS = [
  { href: "/", label: "Triage" },
  { href: "/scout", label: "Scout" },
  { href: "/batch", label: "Batch" },
  { href: "/edgar", label: "EDGAR" },
  { href: "/startups", label: "Startups" },
  { href: "/investors", label: "Investors" },
  { href: "/experts", label: "Experts" },
  { href: "/templates", label: "Templates" },
  { href: "/users", label: "Users" },
  { href: "/feedback", label: "Feedback" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();

  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-surface border-r border-border flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2">
          <LogoIcon size={24} />
          <h1 className="font-serif text-lg text-text-primary">Deep Thesis</h1>
        </div>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block px-3 py-2 rounded text-sm transition ${
                isActive
                  ? "bg-accent text-white"
                  : "text-text-secondary hover:text-text-primary hover:bg-hover-row"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-border">
        <p className="text-xs text-text-tertiary truncate">{session?.user?.email}</p>
        <button
          onClick={() => signOut()}
          className="mt-2 text-xs text-text-secondary hover:text-text-primary transition"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
