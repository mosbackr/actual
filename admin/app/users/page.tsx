"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/StatusBadge";
import { adminApi } from "@/lib/api";
import type { AdminUser } from "@/lib/types";

const ROLES = ["all", "user", "expert", "superadmin"];

export default function UsersPage() {
  const { data: session, status } = useSession();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roleFilter, setRoleFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      const role = roleFilter === "all" ? undefined : roleFilter;
      adminApi.getUsers(session.backendToken, role).then(setUsers).finally(() => setLoading(false));
    }
  }, [session?.backendToken, roleFilter]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const columns = [
    { key: "email", label: "Email" },
    { key: "name", label: "Name" },
    {
      key: "role",
      label: "Role",
      render: (u: Record<string, unknown>) => <StatusBadge status={String(u.role)} />,
    },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Users</h2>
        <div className="flex gap-2 mb-4">
          {ROLES.map((r) => (
            <button
              key={r}
              onClick={() => { setRoleFilter(r); setLoading(true); }}
              className={`px-3 py-1 text-sm rounded ${
                roleFilter === r
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <DataTable columns={columns} data={users as unknown as Record<string, unknown>[]} keyField="id" />
        )}
      </main>
    </div>
  );
}
