"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { adminApi } from "@/lib/api";

type Tab = "locations" | "investors" | "startups";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
};

const STATUS_COLORS: Record<string, string> = {
  running: "bg-yellow-100 text-yellow-800",
  paused: "bg-orange-100 text-orange-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-gray-100 text-gray-600",
  pending: "bg-gray-100 text-gray-600",
};

const PIPELINE_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  none: "bg-gray-100 text-gray-600",
  running: "bg-yellow-100 text-yellow-800",
  complete: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

function Badge({ status }: { status: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status] || "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default function BatchPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  const [job, setJob] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("locations");
  const [locations, setLocations] = useState<any[]>([]);
  const [investors, setInvestors] = useState<any[]>([]);
  const [startups, setStartups] = useState<any[]>([]);
  const [log, setLog] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshDays, setRefreshDays] = useState(30);
  const [elapsed, setElapsed] = useState(0);

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const activeJob = await adminApi.getActiveBatch(token);
      setJob(activeJob);
      if (activeJob?.id) {
        setElapsed(activeJob.elapsed_seconds || 0);

        // Fetch tab data
        if (tab === "locations") {
          const steps = await adminApi.getBatchSteps(token, activeJob.id, "step_type=discover_investors&per_page=500");
          setLocations(steps.items || []);
        } else if (tab === "investors") {
          const inv = await adminApi.getBatchInvestors(token, activeJob.id);
          setInvestors(inv.items || []);
        } else if (tab === "startups") {
          const st = await adminApi.getBatchStartups(token, activeJob.id);
          setStartups(st.items || []);
        }

        // Always fetch log
        const logData = await adminApi.getBatchLog(token, activeJob.id);
        setLog(logData.items || []);
      }
    } catch {
      // silent
    }
  }, [token, tab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Polling
  useEffect(() => {
    const interval = job?.status === "running" ? 5000 : 30000;
    const timer = setInterval(fetchData, interval);
    return () => clearInterval(timer);
  }, [fetchData, job?.status]);

  // Elapsed time counter
  useEffect(() => {
    if (job?.status !== "running") return;
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(timer);
  }, [job?.status]);

  async function handleStart(jobType: string) {
    if (!token) return;
    setLoading(true);
    try {
      await adminApi.startBatch(token, jobType, jobType === "refresh" ? refreshDays : undefined);
      await fetchData();
    } catch (e: any) {
      alert(e.message || "Failed to start batch");
    }
    setLoading(false);
  }

  async function handlePause() {
    if (!token || !job) return;
    await adminApi.pauseBatch(token, job.id);
    await fetchData();
  }

  async function handleResume() {
    if (!token || !job) return;
    await adminApi.resumeBatch(token, job.id);
    await fetchData();
  }

  async function handleCancel() {
    if (!token || !job) return;
    if (!confirm("Cancel this batch job?")) return;
    await adminApi.cancelBatch(token, job.id);
    await fetchData();
  }

  const summary = job?.progress_summary || {};
  const isActive = job?.status === "running" || job?.status === "paused";
  const canStart = !isActive && job?.status !== "pending";

  return (
    <div className="ml-56 p-8">
      <h1 className="font-serif text-2xl text-text-primary mb-6">Batch Pipeline</h1>

      {/* Control Bar */}
      <div className="rounded border border-border bg-surface p-5 mb-6">
        <div className="flex items-center gap-3 mb-4">
          {canStart && (
            <>
              <button
                onClick={() => handleStart("initial")}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
              >
                Start Initial Batch
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleStart("refresh")}
                  disabled={loading}
                  className="px-4 py-2 text-sm font-medium rounded border border-accent text-accent hover:bg-accent/5 disabled:opacity-50 transition"
                >
                  Start Refresh
                </button>
                <input
                  type="number"
                  value={refreshDays}
                  onChange={(e) => setRefreshDays(parseInt(e.target.value) || 30)}
                  className="w-16 px-2 py-2 text-sm rounded border border-border bg-surface text-text-primary"
                  min={1}
                  max={90}
                />
                <span className="text-xs text-text-tertiary">days</span>
              </div>
            </>
          )}
          {job?.status === "running" && (
            <button onClick={handlePause} className="px-4 py-2 text-sm font-medium rounded border border-border text-text-secondary hover:text-text-primary transition">
              Pause
            </button>
          )}
          {(job?.status === "paused" || job?.status === "cancelled") && (
            <button onClick={handleResume} className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition">
              Resume
            </button>
          )}
          {isActive && (
            <button onClick={handleCancel} className="px-4 py-2 text-sm font-medium rounded border border-red-300 text-red-600 hover:bg-red-50 transition">
              Cancel
            </button>
          )}
          {job && <Badge status={job.status} />}
          {job?.error && <span className="text-xs text-red-600 ml-2">{job.error}</span>}
          {isActive && (
            <span className="text-xs text-text-tertiary ml-auto tabular-nums">{formatElapsed(elapsed)}</span>
          )}
        </div>

        {/* Summary stats */}
        {job && (
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            <div>
              <p className="text-xs text-text-tertiary">Locations</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">
                {summary.locations_completed || 0} / {summary.locations_total || 0}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Investors</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">{summary.investors_found || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Startups Found</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">{summary.startups_found || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Added</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">{summary.startups_added || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Enriched</p>
              <p className="text-sm font-medium text-score-high tabular-nums">{summary.startups_enriched || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Duplicates</p>
              <p className="text-sm font-medium text-text-tertiary tabular-nums">{summary.startups_skipped_duplicate || 0}</p>
            </div>
          </div>
        )}

        {job && summary.current_location && (
          <p className="text-xs text-text-tertiary mt-3">
            Currently: {summary.current_location}
            {summary.current_stage && ` / ${STAGE_LABELS[summary.current_stage] || summary.current_stage}`}
            {summary.current_investor && ` / ${summary.current_investor}`}
            {summary.current_startup && ` / ${summary.current_startup}`}
          </p>
        )}
      </div>

      {job && (
        <>
          {/* Tabs */}
          <div className="flex items-center gap-1 mb-4 border-b border-border">
            {(["locations", "investors", "startups"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
                  tab === t
                    ? "border-accent text-accent"
                    : "border-transparent text-text-tertiary hover:text-text-secondary"
                }`}
              >
                {t === "locations" ? "Locations" : t === "investors" ? "Investors" : "Startups"}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="rounded border border-border bg-surface overflow-x-auto mb-6">
            {tab === "locations" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Location</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Investors</th>
                  </tr>
                </thead>
                <tbody>
                  {locations.map((s, i) => {
                    const loc = `${s.params?.city || ""}, ${s.params?.state || s.params?.country || ""}`;
                    const investorCount = (s.result?.investors || []).length;
                    return (
                      <tr
                        key={i}
                        className={`border-b border-border last:border-b-0 ${
                          s.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"
                        }`}
                      >
                        <td className="px-4 py-2 text-text-primary">{loc}</td>
                        <td className="px-4 py-2 text-text-secondary">{STAGE_LABELS[s.params?.stage] || s.params?.stage}</td>
                        <td className="px-4 py-2"><Badge status={s.status} /></td>
                        <td className="px-4 py-2 text-right text-text-secondary tabular-nums">
                          {s.status === "completed" ? investorCount : "\u2014"}
                        </td>
                      </tr>
                    );
                  })}
                  {locations.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">No location steps yet</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {tab === "investors" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Investor</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Location</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Startups</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {investors.map((inv, i) => (
                    <tr key={i} className={`border-b border-border last:border-b-0 ${inv.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"}`}>
                      <td className="px-4 py-2 text-text-primary font-medium">{inv.name}</td>
                      <td className="px-4 py-2 text-text-secondary">{inv.city}, {inv.state || inv.country}</td>
                      <td className="px-4 py-2 text-text-secondary">{STAGE_LABELS[inv.stage] || inv.stage}</td>
                      <td className="px-4 py-2 text-right text-text-secondary tabular-nums">{inv.startups_found}</td>
                      <td className="px-4 py-2"><Badge status={inv.status} /></td>
                    </tr>
                  ))}
                  {investors.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-text-tertiary text-sm">No investors discovered yet</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {tab === "startups" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Startup</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Source Investor</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Pipeline</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">AI Score</th>
                  </tr>
                </thead>
                <tbody>
                  {startups.map((s, i) => (
                    <tr key={i} className="border-b border-border last:border-b-0 hover:bg-hover-row">
                      <td className="px-4 py-2 text-text-primary font-medium">{s.name}</td>
                      <td className="px-4 py-2 text-text-secondary">{s.source_investor}</td>
                      <td className="px-4 py-2 text-text-secondary">{STAGE_LABELS[s.stage] || s.stage}</td>
                      <td className="px-4 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${PIPELINE_COLORS[s.enrichment_status] || "bg-gray-100 text-gray-600"}`}>
                          {s.enrichment_status === "complete" ? "Enriched" : s.enrichment_status === "running" ? "Enriching" : s.enrichment_status === "failed" ? "Failed" : "Triage"}
                        </span>
                        {s.enrich_error && (
                          <span className="text-xs text-red-500 ml-1" title={s.enrich_error}>(!)</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {s.ai_score != null ? (
                          <span className={s.ai_score >= 70 ? "text-score-high" : s.ai_score >= 40 ? "text-score-mid" : "text-score-low"}>
                            {s.ai_score.toFixed(0)}
                          </span>
                        ) : "\u2014"}
                      </td>
                    </tr>
                  ))}
                  {startups.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-text-tertiary text-sm">No startups added yet</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </div>

          {/* Live Log */}
          <div className="rounded border border-border bg-surface">
            <div className="px-4 py-2.5 border-b border-border bg-background">
              <h3 className="text-xs font-medium text-text-tertiary">Activity Log</h3>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {log.map((entry, i) => (
                <div key={i} className="px-4 py-2 border-b border-border last:border-b-0 flex items-start gap-3">
                  <span className="text-xs text-text-tertiary tabular-nums whitespace-nowrap mt-0.5">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`text-sm ${entry.status === "failed" ? "text-red-600" : "text-text-primary"}`}>
                    {entry.message}
                  </span>
                </div>
              ))}
              {log.length === 0 && (
                <div className="px-4 py-8 text-center text-text-tertiary text-sm">No activity yet</div>
              )}
            </div>
          </div>
        </>
      )}

      {!job && (
        <div className="text-center py-20 text-text-tertiary text-sm">
          No batch jobs yet. Start an initial batch to begin discovering investors and startups.
        </div>
      )}
    </div>
  );
}
