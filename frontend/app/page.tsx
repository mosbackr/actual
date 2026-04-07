import { Suspense } from "react";
import { FilterBar } from "@/components/FilterBar";
import { StartupCard } from "@/components/StartupCard";
import type { PaginatedStartups } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getStartups(
  searchParams: Record<string, string | string[] | undefined>
): Promise<PaginatedStartups> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === "string") {
      params.set(key, value);
    }
  }
  const res = await fetch(`${API_URL}/api/startups?${params}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    return { total: 0, page: 1, per_page: 20, pages: 0, items: [] };
  }
  return res.json();
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const data = await getStartups(params);

  // Build flat string params for pagination links
  const linkParams: Record<string, string> = {};
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string") {
      linkParams[key] = value;
    }
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Discover Startups</h1>
        <p className="text-gray-400">
          AI-scored, expert-reviewed startup investment intelligence.
        </p>
      </div>

      <Suspense fallback={<div>Loading filters...</div>}>
        <FilterBar />
      </Suspense>

      {data.items.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <p className="text-lg">No startups found</p>
          <p className="text-sm mt-2">Try adjusting your filters</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {data.items.map((startup) => (
              <StartupCard key={startup.id} startup={startup} />
            ))}
          </div>
          {data.pages > 1 && (
            <div className="mt-8 flex justify-center gap-2">
              {Array.from({ length: data.pages }, (_, i) => i + 1).map((p) => (
                <a
                  key={p}
                  href={`/?${new URLSearchParams({ ...linkParams, page: String(p) })}`}
                  className={`px-3 py-1 rounded text-sm ${
                    p === data.page
                      ? "bg-indigo-600 text-white"
                      : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                  }`}
                >
                  {p}
                </a>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
