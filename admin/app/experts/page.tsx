"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StatusBadge } from "@/components/StatusBadge";
import { adminApi } from "@/lib/api";
import type { ExpertApplication } from "@/lib/types";

export default function ExpertsPage() {
  const { data: session, status } = useSession();
  const [applications, setApplications] = useState<ExpertApplication[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getApplications(session.backendToken).then(setApplications).finally(() => setLoading(false));
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Expert Applications</h2>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-3">
            {applications.map((app) => (
              <div key={app.id} className="border border-gray-800 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <Link href={`/experts/${app.id}`} className="font-medium text-indigo-400 hover:text-indigo-300">
                    Application {app.id.slice(0, 8)}...
                  </Link>
                  <StatusBadge status={app.application_status} />
                </div>
                <p className="text-sm text-gray-400">{app.bio}</p>
                <p className="text-xs text-gray-500 mt-1">{app.years_experience} years experience</p>
                {app.application_status === "pending" && (
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={async () => {
                        await adminApi.approveExpert(session.backendToken!, app.id);
                        setApplications((prev) => prev.filter((a) => a.id !== app.id));
                      }}
                      className="px-3 py-1 text-xs bg-emerald-700 text-white rounded hover:bg-emerald-600"
                    >
                      Approve
                    </button>
                    <button
                      onClick={async () => {
                        await adminApi.rejectExpert(session.backendToken!, app.id);
                        setApplications((prev) => prev.filter((a) => a.id !== app.id));
                      }}
                      className="px-3 py-1 text-xs bg-red-700 text-white rounded hover:bg-red-600"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
            {applications.length === 0 && (
              <p className="text-gray-500 text-center py-8">No pending applications</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
