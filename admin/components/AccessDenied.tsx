"use client";

import { signIn, signOut, useSession } from "next-auth/react";

export function AccessDenied() {
  const { data: session } = useSession();

  if (!session) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <h1 className="font-serif text-2xl text-text-primary mb-4">Deep Thesis Admin</h1>
          <p className="text-text-secondary mb-6">Sign in to access the admin panel.</p>
          <button
            onClick={() => signIn()}
            className="px-6 py-2 bg-accent text-white rounded hover:bg-accent-hover transition"
          >
            Sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h1 className="font-serif text-2xl text-text-primary mb-4">Access Denied</h1>
        <p className="text-text-secondary mb-2">
          Signed in as {session.user?.email}
        </p>
        <p className="text-text-tertiary mb-6">
          You need superadmin privileges to access this panel.
        </p>
        <button
          onClick={() => signOut()}
          className="px-6 py-2 border border-border text-text-secondary rounded hover:text-text-primary hover:border-text-tertiary transition"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
