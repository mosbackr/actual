"use client";

import { signIn, signOut, useSession } from "next-auth/react";

export function AccessDenied() {
  const { data: session } = useSession();

  if (!session) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4">Acutal Admin</h1>
          <p className="text-gray-400 mb-6">Sign in to access the admin panel.</p>
          <button
            onClick={() => signIn()}
            className="px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
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
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p className="text-gray-400 mb-2">
          Signed in as {session.user?.email}
        </p>
        <p className="text-gray-500 mb-6">
          You need superadmin privileges to access this panel.
        </p>
        <button
          onClick={() => signOut()}
          className="px-6 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
