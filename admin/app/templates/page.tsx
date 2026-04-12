"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { adminApi } from "@/lib/api";
import type { DDTemplate } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
};

export default function TemplatesPage() {
  const { data: session, status } = useSession();
  const [templates, setTemplates] = useState<DDTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "industry" | "stage" | "general">("all");

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getTemplates(session.backendToken).then(setTemplates).finally(() => setLoading(false));
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const filtered = templates.filter((t) => {
    if (filter === "industry") return t.industry_slug && !t.stage;
    if (filter === "stage") return t.stage && !t.industry_slug;
    if (filter === "general") return !t.industry_slug && !t.stage;
    return true;
  });

  const filterClasses = (active: boolean) =>
    `px-3 py-1 text-sm rounded transition ${active ? "bg-accent text-white" : "border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary"}`;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-serif text-xl text-text-primary">DD Templates</h2>
          <Link
            href="/templates/new"
            className="px-3 py-1 text-sm bg-accent text-white rounded hover:bg-accent-hover transition"
          >
            + New Template
          </Link>
        </div>

        <div className="flex gap-2 mb-4">
          <button onClick={() => setFilter("all")} className={filterClasses(filter === "all")}>All</button>
          <button onClick={() => setFilter("industry")} className={filterClasses(filter === "industry")}>By Industry</button>
          <button onClick={() => setFilter("stage")} className={filterClasses(filter === "stage")}>By Stage</button>
          <button onClick={() => setFilter("general")} className={filterClasses(filter === "general")}>General</button>
        </div>

        {loading ? (
          <p className="text-text-tertiary">Loading...</p>
        ) : (
          <div className="space-y-3">
            {filtered.map((t) => (
              <Link
                key={t.id}
                href={`/templates/${t.id}`}
                className="block border border-border rounded p-4 hover:border-text-tertiary transition-colors"
              >
                <div className="flex items-center gap-2">
                  <h3 className="font-medium text-text-primary">{t.name}</h3>
                  {t.industry_slug && (
                    <span className="px-2 py-0.5 text-xs rounded bg-accent/10 text-accent">
                      {t.industry_slug}
                    </span>
                  )}
                  {t.stage && (
                    <span className="px-2 py-0.5 text-xs rounded bg-score-mid/20 text-score-mid">
                      {STAGE_LABELS[t.stage] || t.stage}
                    </span>
                  )}
                </div>
                {t.description && <p className="text-sm text-text-secondary mt-1">{t.description}</p>}
                <p className="text-xs text-text-tertiary mt-1">{t.dimensions.length} dimensions</p>
              </Link>
            ))}
            {filtered.length === 0 && (
              <p className="text-text-tertiary text-center py-8">No templates match this filter</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
