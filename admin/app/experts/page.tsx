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
        <h2 className="font-serif text-xl text-text-primary mb-4">Expert Applications</h2>
        {loading ? (
          <p className="text-text-tertiary">Loading...</p>
        ) : (
          <div className="space-y-3">
            {applications.map((app) => (
              <div key={app.id} className="border border-border rounded p-4">
                <div className="flex items-center justify-between mb-2">
                  <Link href={`/experts/${app.id}`} className="font-medium text-accent hover:text-accent-hover transition">
                    Application {app.id.slice(0, 8)}...
                  </Link>
                  <StatusBadge status={app.application_status} />
                </div>
                <p className="text-sm text-text-secondary">{app.bio}</p>
                <p className="text-xs text-text-tertiary mt-1">{app.years_experience} years experience</p>
                {app.application_status === "pending" && (
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={async () => {
                        await adminApi.approveExpert(session.backendToken!, app.id);
                        setApplications((prev) => prev.filter((a) => a.id !== app.id));
                      }}
                      className="px-3 py-1 text-xs bg-score-high text-white rounded hover:opacity-90 transition"
                    >
                      Approve
                    </button>
                    <button
                      onClick={async () => {
                        await adminApi.rejectExpert(session.backendToken!, app.id);
                        setApplications((prev) => prev.filter((a) => a.id !== app.id));
                      }}
                      className="px-3 py-1 text-xs bg-score-low text-white rounded hover:opacity-90 transition"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
            {applications.length === 0 && (
              <p className="text-text-tertiary text-center py-8">No pending applications</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
