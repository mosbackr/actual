"use client";

import { signIn, signOut, useSession } from "next-auth/react";

export function AuthButton() {
  const { data: session } = useSession();

  if (session) {
    return (
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-300">{session.user?.name}</span>
        <button
          onClick={() => signOut()}
          className="text-sm px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-white transition"
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => signIn()}
      className="text-sm px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white transition"
    >
      Sign In
    </button>
  );
}
