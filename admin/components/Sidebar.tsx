"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";

const NAV_ITEMS = [
  { href: "/", label: "Triage" },
  { href: "/startups", label: "Startups" },
  { href: "/experts", label: "Experts" },
  { href: "/templates", label: "Templates" },
  { href: "/users", label: "Users" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();

  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-gray-950 border-r border-gray-800 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold text-indigo-400">Acutal Admin</h1>
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
              className={`block px-3 py-2 rounded text-sm ${
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-800">
        <p className="text-xs text-gray-500 truncate">{session?.user?.email}</p>
        <button
          onClick={() => signOut()}
          className="mt-2 text-xs text-gray-400 hover:text-white"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
