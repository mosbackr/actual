"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { TriageFeedCard } from "@/components/TriageFeedCard";
import { adminApi } from "@/lib/api";
import type { TriageItem } from "@/lib/types";

type FilterTab = "all" | "startups";

export default function TriagePage() {
  const { data: session, status } = useSession();
  const [items, setItems] = useState<TriageItem[]>([]);
  const [filter, setFilter] = useState<FilterTab>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      loadFeed();
    }
  }, [session?.backendToken]);

  async function loadFeed() {
    if (!session?.backendToken) return;
    setLoading(true);
    try {
      const startups = await adminApi.getPipeline(session.backendToken);

      const feed: TriageItem[] = startups.map((s): TriageItem => ({
        type: "startup",
        id: s.id,
        timestamp: s.created_at,
        data: s,
      }));

      feed.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setItems(feed);
    } catch (err) {
      console.error("Failed to load feed:", err);
    } finally {
      setLoading(false);
    }
  }

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const filtered = filter === "all"
    ? items
    : items.filter((i) => i.type === "startup");

  async function handleApproveStartup(id: string) {
    if (!session?.backendToken) return;
    await adminApi.updateStartup(session.backendToken, id, { status: "approved" });
    loadFeed();
  }

  async function handleRejectStartup(id: string) {
    if (!session?.backendToken) return;
    await adminApi.updateStartup(session.backendToken, id, { status: "rejected" });
    loadFeed();
  }

  const tabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "startups", label: "Startups" },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="font-serif text-xl text-text-primary mb-4">Triage Feed</h2>
        <div className="flex gap-2 mb-4">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`px-3 py-1 text-sm rounded transition ${
                filter === tab.key
                  ? "bg-accent text-white"
                  : "border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {loading ? (
          <p className="text-text-tertiary">Loading...</p>
        ) : (
          <div className="space-y-3">
            {filtered.map((item) => (
              <TriageFeedCard
                key={`${item.type}-${item.id}`}
                item={item}
                onApproveStartup={handleApproveStartup}
                onRejectStartup={handleRejectStartup}
                onApproveExpert={() => {}}
                onRejectExpert={() => {}}
              />
            ))}
            {filtered.length === 0 && (
              <p className="text-text-tertiary text-center py-8">No items to review</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
