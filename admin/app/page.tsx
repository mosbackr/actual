"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { TriageFeedCard } from "@/components/TriageFeedCard";
import { adminApi } from "@/lib/api";
import type { TriageItem } from "@/lib/types";

type FilterTab = "all" | "startups" | "experts" | "assignments";

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
      const [startups, applications] = await Promise.all([
        adminApi.getPipeline(session.backendToken),
        adminApi.getApplications(session.backendToken),
      ]);

      const feed: TriageItem[] = [
        ...startups.map((s): TriageItem => ({
          type: "startup",
          id: s.id,
          timestamp: s.created_at,
          data: s,
        })),
        ...applications.map((e): TriageItem => ({
          type: "expert_application",
          id: e.id,
          timestamp: e.created_at,
          data: e,
        })),
      ];

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
    : items.filter((i) =>
        filter === "startups" ? i.type === "startup"
        : filter === "experts" ? i.type === "expert_application"
        : i.type === "assignment"
      );

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

  async function handleApproveExpert(id: string) {
    if (!session?.backendToken) return;
    await adminApi.approveExpert(session.backendToken, id);
    loadFeed();
  }

  async function handleRejectExpert(id: string) {
    if (!session?.backendToken) return;
    await adminApi.rejectExpert(session.backendToken, id);
    loadFeed();
  }

  const tabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "startups", label: "Startups" },
    { key: "experts", label: "Experts" },
    { key: "assignments", label: "Assignments" },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Triage Feed</h2>
        <div className="flex gap-2 mb-4">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`px-3 py-1 text-sm rounded ${
                filter === tab.key
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-3">
            {filtered.map((item) => (
              <TriageFeedCard
                key={`${item.type}-${item.id}`}
                item={item}
                onApproveStartup={handleApproveStartup}
                onRejectStartup={handleRejectStartup}
                onApproveExpert={handleApproveExpert}
                onRejectExpert={handleRejectExpert}
              />
            ))}
            {filtered.length === 0 && (
              <p className="text-gray-500 text-center py-8">No items to review</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
