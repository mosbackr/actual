"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/DataTable";
import { adminApi } from "@/lib/api";
import type { AdminStartup } from "@/lib/types";

export default function StartupsPage() {
  const { data: session, status } = useSession();
  const [startups, setStartups] = useState<AdminStartup[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    if (session?.backendToken) {
      setLoading(true);
      adminApi
        .getAllStartups(session.backendToken, statusFilter || undefined)
        .then(setStartups)
        .finally(() => setLoading(false));
    }
  }, [session?.backendToken, statusFilter]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const columns = [
    {
      key: "name",
      label: "Name",
      render: (s: Record<string, unknown>) => (
        <div className="flex items-center gap-2">
          {s.logo_url ? (
            <img
              src={String(s.logo_url)}
              alt=""
              className="w-6 h-6 rounded border border-border object-contain bg-white shrink-0"
            />
          ) : (
            <div className="w-6 h-6 rounded border border-border bg-hover-row shrink-0" />
          )}
          <Link href={`/startups/${s.id}`} className="text-accent hover:text-accent-hover transition">
            {String(s.name)}
          </Link>
        </div>
      ),
    },
    { key: "stage", label: "Stage" },
    {
      key: "status",
      label: "Status",
      render: (s: Record<string, unknown>) => <StatusBadge status={String(s.status)} />,
    },
    {
      key: "industries",
      label: "Industries",
      render: (s: Record<string, unknown>) => {
        const industries = s.industries as { name: string }[];
        return (
          <span className="text-text-tertiary text-sm">
            {industries.length > 0 ? industries.map((i) => i.name).join(", ") : "\u2014"}
          </span>
        );
      },
    },
    { key: "created_at", label: "Created" },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-serif text-xl text-text-primary">Startups</h2>
          <div className="flex items-center gap-3">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-surface border border-border rounded px-3 py-1.5 text-sm text-text-secondary focus:border-accent outline-none"
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="featured">Featured</option>
              <option value="rejected">Rejected</option>
            </select>
            <Link
              href="/startups/new"
              className="px-4 py-1.5 bg-accent text-white text-sm rounded hover:bg-accent-hover transition"
            >
              + New Startup
            </Link>
          </div>
        </div>
        {loading ? (
          <p className="text-text-tertiary">Loading...</p>
        ) : startups.length === 0 ? (
          <p className="text-text-tertiary">No startups found.</p>
        ) : (
          <DataTable columns={columns} data={startups as unknown as Record<string, unknown>[]} keyField="id" />
        )}
      </main>
    </div>
  );
}
