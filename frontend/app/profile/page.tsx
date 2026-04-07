"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ExpertApplication } from "@/lib/types";

export default function ProfilePage() {
  const { data: session } = useSession();
  const [application, setApplication] = useState<ExpertApplication | null>(
    null
  );

  useEffect(() => {
    if (!session) return;
    const token = (session as any).accessToken;
    if (token) {
      api
        .getMyApplication(token)
        .then(setApplication)
        .catch(() => {});
    }
  }, [session]);

  if (!session) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400">Please sign in to view your profile.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto py-10">
      <h1 className="text-2xl font-bold mb-6">Profile</h1>

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 mb-8">
        <div className="flex items-center gap-4">
          {session.user?.image && (
            <img
              src={session.user.image}
              alt=""
              className="h-16 w-16 rounded-full"
            />
          )}
          <div>
            <h2 className="text-lg font-semibold">{session.user?.name}</h2>
            <p className="text-sm text-gray-400">{session.user?.email}</p>
          </div>
        </div>
      </div>

      {application && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
          <h3 className="font-semibold mb-3">Expert Application</h3>
          <p className="text-sm text-gray-400">
            Status:{" "}
            <span
              className={
                application.application_status === "approved"
                  ? "text-emerald-400"
                  : application.application_status === "rejected"
                    ? "text-red-400"
                    : "text-yellow-400"
              }
            >
              {application.application_status}
            </span>
          </p>
          <p className="text-sm text-gray-400 mt-1">
            Industries: {application.industries.join(", ")}
          </p>
          <p className="text-sm text-gray-400 mt-1">
            Skills: {application.skills.join(", ")}
          </p>
        </div>
      )}
    </div>
  );
}
