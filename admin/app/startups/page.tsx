"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/DataTable";
import { adminApi } from "@/lib/api";
import type { PipelineStartup } from "@/lib/types";

export default function StartupsPage() {
  const { data: session, status } = useSession();
  const [startups, setStartups] = useState<PipelineStartup[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getPipeline(session.backendToken).then(setStartups).finally(() => setLoading(false));
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const columns = [
    {
      key: "name",
      label: "Name",
      render: (s: Record<string, unknown>) => (
        <Link href={`/startups/${s.id}`} className="text-indigo-400 hover:text-indigo-300">
          {String(s.name)}
        </Link>
      ),
    },
    { key: "stage", label: "Stage" },
    {
      key: "status",
      label: "Status",
      render: (s: Record<string, unknown>) => <StatusBadge status={String(s.status)} />,
    },
    { key: "assignment_count", label: "Assignments" },
    {
      key: "dimensions_configured",
      label: "Dimensions",
      render: (s: Record<string, unknown>) => (
        <span className={s.dimensions_configured ? "text-emerald-400" : "text-gray-500"}>
          {s.dimensions_configured ? "Yes" : "No"}
        </span>
      ),
    },
    { key: "created_at", label: "Created" },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Startups</h2>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <DataTable columns={columns} data={startups as unknown as Record<string, unknown>[]} keyField="id" />
        )}
      </main>
    </div>
  );
}
