"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { adminApi } from "@/lib/api";
import type { DDTemplate } from "@/lib/types";

export default function TemplatesPage() {
  const { data: session, status } = useSession();
  const [templates, setTemplates] = useState<DDTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getTemplates(session.backendToken).then(setTemplates).finally(() => setLoading(false));
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">DD Templates</h2>
          <Link
            href="/templates/new"
            className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            + New Template
          </Link>
        </div>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-3">
            {templates.map((t) => (
              <Link
                key={t.id}
                href={`/templates/${t.id}`}
                className="block border border-gray-800 rounded-lg p-4 hover:border-gray-700"
              >
                <h3 className="font-medium text-white">{t.name}</h3>
                {t.description && <p className="text-sm text-gray-400 mt-1">{t.description}</p>}
                <p className="text-xs text-gray-500 mt-1">{t.dimensions.length} dimensions</p>
              </Link>
            ))}
            {templates.length === 0 && (
              <p className="text-gray-500 text-center py-8">No templates yet</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
