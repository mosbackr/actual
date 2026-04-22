"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { AccessDenied } from "@/components/AccessDenied";
import type { InvestorItem, InvestorBatchStatus } from "@/lib/types";

export default function InvestorsPage() {
  const { data: session, status } = useSession();
  const token = session?.backendToken;

  // Batch state
  const [batchStatus, setBatchStatus] = useState<InvestorBatchStatus | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);

  // List state
  const [investors, setInvestors] = useState<InvestorItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);

  // Expanded row
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchBatchStatus = useCallback(async () => {
    if (!token) return;
    try {
      const status = await adminApi.getInvestorBatchStatus(token);
      setBatchStatus(status);
    } catch {}
  }, [token]);

  const fetchInvestors = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await adminApi.getInvestors(token, {
        q: search || undefined,
        page,
        per_page: 50,
      });
      setInvestors(data.items);
      setTotal(data.total);
      setPages(data.pages);
    } catch {}
    setLoading(false);
  }, [token, search, page]);

  useEffect(() => {
    fetchBatchStatus();
    fetchInvestors();
  }, [fetchBatchStatus, fetchInvestors]);

  // Poll batch status while running
  useEffect(() => {
    if (!batchStatus || batchStatus.status !== "running") return;
    const interval = setInterval(() => {
      fetchBatchStatus();
      fetchInvestors();
    }, 5000);
    return () => clearInterval(interval);
  }, [batchStatus?.status, fetchBatchStatus, fetchInvestors]);

  async function startBatch() {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.startInvestorBatch(token);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to start batch");
    }
    setBatchLoading(false);
  }

  async function pauseBatch() {
    if (!token || !batchStatus) return;
    setBatchLoading(true);
    try {
      await adminApi.pauseInvestorBatch(token, batchStatus.id);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to pause");
    }
    setBatchLoading(false);
  }

  async function resumeBatch() {
    if (!token || !batchStatus) return;
    setBatchLoading(true);
    try {
      await adminApi.resumeInvestorBatch(token, batchStatus.id);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to resume");
    }
    setBatchLoading(false);
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  }

  const isRunning = batchStatus?.status === "running";
  const isPaused = batchStatus?.status === "paused";
  const progressPct =
    batchStatus && batchStatus.total_startups > 0
      ? Math.round((batchStatus.processed_startups / batchStatus.total_startups) * 100)
      : 0;

  if (status === "loading") return null;
  if (!session || (session as any).role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Investors</h1>
          <p className="text-sm text-text-secondary mt-1">
            {total.toLocaleString()} investors in database
          </p>
        </div>
        <div className="flex gap-2">
          <span className="px-4 py-2 text-sm bg-accent text-white rounded">
            Investors
          </span>
          <Link
            href="/investors/rankings"
            className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
          >
            Rankings
          </Link>
        </div>
      </div>

      {/* Batch Controls */}
      <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-medium text-text-primary">Investor Extraction</h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              Uses Perplexity to find ~200 investors per pre-seed/seed startup
            </p>
          </div>
          <div className="flex items-center gap-2">
            {!isRunning && !isPaused && (
              <button
                onClick={startBatch}
                disabled={batchLoading}
                className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
              >
                {batchLoading ? "Starting..." : "Extract Investors"}
              </button>
            )}
            {isRunning && (
              <button
                onClick={pauseBatch}
                disabled={batchLoading}
                className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition disabled:opacity-50"
              >
                Pause
              </button>
            )}
            {isPaused && (
              <button
                onClick={resumeBatch}
                disabled={batchLoading}
                className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
              >
                Resume
              </button>
            )}
          </div>
        </div>

        {(isRunning || isPaused) && batchStatus && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
              <span>
                {batchStatus.processed_startups}/{batchStatus.total_startups} startups
                {batchStatus.current_startup_name && isRunning && (
                  <> — processing <strong>{batchStatus.current_startup_name}</strong></>
                )}
                {isPaused && " — paused"}
              </span>
              <span>{batchStatus.investors_found.toLocaleString()} investors found</span>
            </div>
            <div className="w-full bg-background rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${isPaused ? "bg-text-tertiary" : "bg-accent"}`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        )}

        {batchStatus?.status === "completed" && (
          <p className="text-xs text-text-tertiary mt-2">
            Last batch completed — {batchStatus.investors_found.toLocaleString()} investors found
            from {batchStatus.total_startups} startups
          </p>
        )}
        {batchStatus?.status === "failed" && (
          <p className="text-xs text-red-500 mt-2">
            Batch failed: {batchStatus.error}
          </p>
        )}
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="Search firm, partner, or email..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="flex-1 px-3 py-2 border border-border rounded bg-background text-text-primary text-sm placeholder:text-text-tertiary focus:outline-none focus:border-accent"
        />
        <button
          type="submit"
          className="px-4 py-2 border border-border rounded text-sm text-text-secondary hover:border-text-tertiary transition"
        >
          Search
        </button>
        {search && (
          <button
            type="button"
            onClick={() => {
              setSearchInput("");
              setSearch("");
              setPage(1);
            }}
            className="px-3 py-2 text-xs text-text-tertiary hover:text-text-secondary transition"
          >
            Clear
          </button>
        )}
      </form>

      {/* Table */}
      {loading ? (
        <p className="text-text-tertiary text-sm py-10 text-center">Loading...</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Firm</th>
                  <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Partner</th>
                  <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Email</th>
                  <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Stage Focus</th>
                  <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Sector</th>
                  <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Location</th>
                  <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Sources</th>
                </tr>
              </thead>
              <tbody>
                {investors.map((row) => (
                  <>
                    <tr
                      key={row.id}
                      onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
                      className="border-b border-border hover:bg-hover-row transition-colors cursor-pointer"
                    >
                      <td className="px-3 py-4">
                        <div className="font-medium text-text-primary">{row.firm_name}</div>
                        {row.website && (
                          <a
                            href={row.website.startsWith("http") ? row.website : `https://${row.website}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-accent hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {row.website.replace(/^https?:\/\//, "")}
                          </a>
                        )}
                      </td>
                      <td className="px-3 py-4">{row.partner_name}</td>
                      <td className="px-3 py-4">
                        {row.email ? (
                          <a href={`mailto:${row.email}`} className="text-accent hover:underline text-sm" onClick={(e) => e.stopPropagation()}>
                            {row.email}
                          </a>
                        ) : (
                          <span className="text-text-tertiary">—</span>
                        )}
                      </td>
                      <td className="px-3 py-4">{row.stage_focus || "—"}</td>
                      <td className="px-3 py-4">
                        <span className="text-sm truncate max-w-[200px] block" title={row.sector_focus || ""}>
                          {row.sector_focus || "—"}
                        </span>
                      </td>
                      <td className="px-3 py-4">{row.location || "—"}</td>
                      <td className="px-3 py-4">
                        <span className="inline-flex items-center justify-center px-2 py-0.5 rounded bg-accent/10 text-accent text-xs font-medium">
                          {row.source_startups?.length || 0}
                        </span>
                      </td>
                    </tr>
                    {expandedId === row.id && (
                      <tr key={`${row.id}-detail`}>
                        <td colSpan={7} className="px-3 pb-4">
                          <div className="border border-border rounded-lg p-4 bg-surface">
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div>
                                <span className="text-text-tertiary">AUM / Fund Size:</span>{" "}
                                <span className="text-text-primary">{row.aum_fund_size || "—"}</span>
                              </div>
                              <div>
                                <span className="text-text-tertiary">Location:</span>{" "}
                                <span className="text-text-primary">{row.location || "—"}</span>
                              </div>
                            </div>
                            {row.fit_reason && (
                              <div className="mt-3">
                                <span className="text-xs text-text-tertiary">Fit Reason:</span>
                                <p className="text-sm text-text-primary mt-0.5">{row.fit_reason}</p>
                              </div>
                            )}
                            {row.recent_investments && row.recent_investments.length > 0 && (
                              <div className="mt-3">
                                <span className="text-xs text-text-tertiary">Recent Investments:</span>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {row.recent_investments.map((ri, i) => (
                                    <span
                                      key={i}
                                      className="px-2 py-0.5 text-xs rounded bg-background border border-border text-text-secondary"
                                    >
                                      {ri}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            {row.source_startups && row.source_startups.length > 0 && (
                              <div className="mt-3">
                                <span className="text-xs text-text-tertiary">Source Startups:</span>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {row.source_startups.map((s) => (
                                    <span
                                      key={s.id}
                                      className="px-2 py-0.5 text-xs rounded bg-accent/10 text-accent"
                                    >
                                      {s.name}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
            {investors.length === 0 && (
              <p className="text-center text-text-tertiary py-8">No investors yet</p>
            )}
          </div>

          {/* Pagination */}
          {pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              {page > 1 && (
                <button
                  onClick={() => setPage(page - 1)}
                  className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                >
                  Previous
                </button>
              )}
              <span className="text-sm text-text-tertiary px-3">
                Page {page} of {pages}
              </span>
              {page < pages && (
                <button
                  onClick={() => setPage(page + 1)}
                  className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                >
                  Next
                </button>
              )}
            </div>
          )}
        </>
      )}
      </main>
    </div>
  );
}
