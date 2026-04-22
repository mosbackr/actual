"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { AccessDenied } from "@/components/AccessDenied";
import Link from "next/link";
import type { RankedInvestorItem, RankingBatchStatus } from "@/lib/types";

const SCORE_COLUMNS = [
  { key: "overall_score", label: "Overall" },
  { key: "portfolio_performance", label: "Portfolio" },
  { key: "deal_activity", label: "Activity" },
  { key: "exit_track_record", label: "Exits" },
  { key: "stage_expertise", label: "Stage" },
  { key: "sector_expertise", label: "Sector" },
  { key: "follow_on_rate", label: "Follow-on" },
  { key: "network_quality", label: "Network" },
] as const;

function scoreColor(score: number): string {
  if (score >= 80) return "text-green-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-text-secondary";
  return "text-red-400";
}

export default function InvestorRankingsPage() {
  const { data: session, status } = useSession();
  const token = session?.backendToken;

  const [batchStatus, setBatchStatus] = useState<RankingBatchStatus | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);

  const [investors, setInvestors] = useState<RankedInvestorItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("overall_score");
  const [order, setOrder] = useState("desc");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [rescoring, setRescoring] = useState<string | null>(null);

  const fetchBatchStatus = useCallback(async () => {
    if (!token) return;
    try {
      const s = await adminApi.getRankingBatchStatus(token);
      setBatchStatus(s);
    } catch {}
  }, [token]);

  const fetchRankings = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await adminApi.getRankedInvestors(token, {
        sort,
        order,
        q: search || undefined,
        page,
        per_page: 50,
      });
      setInvestors(data.items);
      setTotal(data.total);
      setPages(data.pages);
    } catch {}
    setLoading(false);
  }, [token, sort, order, search, page]);

  useEffect(() => {
    fetchBatchStatus();
    fetchRankings();
  }, [fetchBatchStatus, fetchRankings]);

  useEffect(() => {
    if (!batchStatus || batchStatus.status !== "running") return;
    const interval = setInterval(() => {
      fetchBatchStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [batchStatus?.status, fetchBatchStatus]);

  async function startBatch() {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.startRankingBatch(token);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to start ranking batch");
    }
    setBatchLoading(false);
  }

  async function pauseBatch() {
    if (!token || !batchStatus) return;
    setBatchLoading(true);
    try {
      await adminApi.pauseRankingBatch(token, batchStatus.id);
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
      await adminApi.resumeRankingBatch(token, batchStatus.id);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to resume");
    }
    setBatchLoading(false);
  }

  async function handleRescore(investorId: string) {
    if (!token) return;
    setRescoring(investorId);
    try {
      await adminApi.rescoreInvestor(token, investorId);
      setTimeout(() => fetchRankings(), 3000);
    } catch (e: any) {
      alert(e.message || "Failed to rescore");
    }
    setRescoring(null);
  }

  function handleSort(key: string) {
    if (sort === key) {
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSort(key);
      setOrder("desc");
    }
    setPage(1);
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  }

  const isRunning = batchStatus?.status === "running";
  const isPaused = batchStatus?.status === "paused";
  const progressPct =
    batchStatus && batchStatus.total_investors > 0
      ? Math.round((batchStatus.processed_investors / batchStatus.total_investors) * 100)
      : 0;

  if (status === "loading") return null;
  if (!session || (session as any).role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-text-primary">Investor Rankings</h1>
            <p className="text-sm text-text-secondary mt-1">
              {total.toLocaleString()} ranked investors
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              href="/investors"
              className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
            >
              Investors
            </Link>
            <span className="px-4 py-2 text-sm bg-accent text-white rounded">
              Rankings
            </span>
          </div>
        </div>

        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-text-primary">Investor Scoring</h2>
              <p className="text-xs text-text-tertiary mt-0.5">
                Uses Perplexity research + Claude scoring across 7 dimensions
              </p>
            </div>
            <div className="flex items-center gap-2">
              {!isRunning && !isPaused && (
                <button
                  onClick={startBatch}
                  disabled={batchLoading}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  {batchLoading ? "Starting..." : "Score All Investors"}
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
                  {batchStatus.processed_investors}/{batchStatus.total_investors} investors
                  {batchStatus.current_investor_name && isRunning && (
                    <> — scoring <strong>{batchStatus.current_investor_name}</strong></>
                  )}
                  {isPaused && " — paused"}
                </span>
                <span>{batchStatus.investors_scored.toLocaleString()} scored</span>
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
              Last batch completed — {batchStatus.investors_scored.toLocaleString()} investors scored
              out of {batchStatus.total_investors}
            </p>
          )}
          {batchStatus?.status === "failed" && (
            <p className="text-xs text-red-500 mt-2">
              Batch failed: {batchStatus.error}
            </p>
          )}
        </div>

        <form onSubmit={handleSearch} className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Search firm or partner..."
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

        {loading ? (
          <p className="text-text-tertiary text-sm py-10 text-center">Loading...</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium w-10">
                      #
                    </th>
                    <th className="text-left px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">
                      <button onClick={() => handleSort("firm_name")} className="hover:text-text-primary transition">
                        Investor {sort === "firm_name" && (order === "asc" ? "↑" : "↓")}
                      </button>
                    </th>
                    {SCORE_COLUMNS.map((col) => (
                      <th key={col.key} className="text-center px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">
                        <button onClick={() => handleSort(col.key)} className="hover:text-text-primary transition">
                          {col.label} {sort === col.key && (order === "asc" ? "↑" : "↓")}
                        </button>
                      </th>
                    ))}
                    <th className="text-left px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">
                      Scored
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {investors.map((row, idx) => (
                    <>
                      <tr
                        key={row.id}
                        onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
                        className="border-b border-border hover:bg-hover-row transition-colors cursor-pointer"
                      >
                        <td className="px-2 py-3 text-text-tertiary tabular-nums">
                          {(page - 1) * 50 + idx + 1}
                        </td>
                        <td className="px-2 py-3">
                          <div className="font-medium text-text-primary">{row.firm_name}</div>
                          <div className="text-xs text-text-tertiary">{row.partner_name}</div>
                        </td>
                        {SCORE_COLUMNS.map((col) => (
                          <td key={col.key} className="px-2 py-3 text-center tabular-nums">
                            <span className={`font-medium ${col.key === "overall_score" ? "text-lg " : "text-sm "}${scoreColor(row[col.key as keyof RankedInvestorItem] as number)}`}>
                              {Math.round(row[col.key as keyof RankedInvestorItem] as number)}
                            </span>
                          </td>
                        ))}
                        <td className="px-2 py-3 text-xs text-text-tertiary">
                          {new Date(row.scored_at).toLocaleDateString()}
                        </td>
                      </tr>
                      {expandedId === row.id && (
                        <tr key={`${row.id}-detail`}>
                          <td colSpan={11} className="px-2 pb-4">
                            <div className="border border-border rounded-lg p-4 bg-surface">
                              <div className="flex items-center justify-between mb-3">
                                <h3 className="text-sm font-medium text-text-primary">
                                  {row.firm_name} — {row.partner_name}
                                </h3>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleRescore(row.investor_id);
                                  }}
                                  disabled={rescoring === row.investor_id}
                                  className="px-3 py-1 text-xs border border-border rounded text-text-secondary hover:border-text-tertiary transition disabled:opacity-50"
                                >
                                  {rescoring === row.investor_id ? "Re-scoring..." : "Re-score"}
                                </button>
                              </div>
                              {row.stage_focus && (
                                <p className="text-xs text-text-tertiary mb-1">
                                  <span className="text-text-secondary">Stage:</span> {row.stage_focus}
                                </p>
                              )}
                              {row.sector_focus && (
                                <p className="text-xs text-text-tertiary mb-1">
                                  <span className="text-text-secondary">Sector:</span> {row.sector_focus}
                                </p>
                              )}
                              {row.location && (
                                <p className="text-xs text-text-tertiary mb-3">
                                  <span className="text-text-secondary">Location:</span> {row.location}
                                </p>
                              )}
                              <div className="border-t border-border pt-3">
                                <h4 className="text-xs font-medium text-text-secondary mb-2">Analyst Note</h4>
                                <div className="text-sm text-text-primary leading-relaxed whitespace-pre-line">
                                  {row.narrative}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
              {investors.length === 0 && (
                <p className="text-center text-text-tertiary py-8">
                  No ranked investors yet. Click "Score All Investors" to start.
                </p>
              )}
            </div>

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
