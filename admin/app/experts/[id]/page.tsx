"use client";

import { useEffect, useState, use } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StatusBadge } from "@/components/StatusBadge";
import { adminApi } from "@/lib/api";
import type { ExpertApplication } from "@/lib/types";

export default function ExpertDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const router = useRouter();
  const [application, setApplication] = useState<ExpertApplication | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getApplications(session.backendToken).then((apps) => {
        setApplication(apps.find((a) => a.id === id) || null);
        setLoading(false);
      });
    }
  }, [session?.backendToken, id]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : !application ? (
          <p className="text-gray-500">Application not found</p>
        ) : (
          <div className="max-w-2xl">
            <div className="flex items-center gap-3 mb-6">
              <h2 className="text-xl font-bold">Expert Application</h2>
              <StatusBadge status={application.application_status} />
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-gray-400">Bio</label>
                <p className="text-white mt-1">{application.bio}</p>
              </div>
              <div>
                <label className="text-sm text-gray-400">Years of Experience</label>
                <p className="text-white mt-1">{application.years_experience}</p>
              </div>
              <div>
                <label className="text-sm text-gray-400">Applied</label>
                <p className="text-white mt-1">{new Date(application.created_at).toLocaleDateString()}</p>
              </div>
            </div>
            {application.application_status === "pending" && (
              <div className="flex gap-3 mt-6">
                <button
                  onClick={async () => {
                    await adminApi.approveExpert(session.backendToken!, id);
                    router.push("/experts");
                  }}
                  className="px-4 py-2 bg-emerald-700 text-white rounded hover:bg-emerald-600"
                >
                  Approve
                </button>
                <button
                  onClick={async () => {
                    await adminApi.rejectExpert(session.backendToken!, id);
                    router.push("/experts");
                  }}
                  className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
