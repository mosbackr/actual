"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";

type Tab = "startups" | "filings";

const PHASE_LABELS: Record<string, string> = {
  resolving_ciks: "Resolving CIKs",
  fetching_filings: "Fetching Filings",
  processing_filings: "Processing Filings",
  complete: "Complete",
  discovering: "Discovering Filings",
  extracting: "Extracting Companies",
  adding: "Creating Startups",
  enriching: "Enriching with Perplexity",
};

const STATUS_COLORS: Record<string, string> = {
  running: "bg-yellow-100 text-yellow-800",
  paused: "bg-orange-100 text-orange-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-gray-100 text-gray-600",
  pending: "bg-gray-100 text-gray-600",
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

export default function EdgarPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  const [job, setJob] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("startups");
  const [startups, setStartups] = useState<any[]>([]);
  const [filings, setFilings] = useState<any[]>([]);
  const [log, setLog] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [discoverDays, setDiscoverDays] = useState(365);
  const [formTypes, setFormTypes] = useState<string[]>(["D", "S-1", "10-K", "C", "1-A"]);

  const FORM_OPTIONS = [
    { value: "D", label: "Form D" },
    { value: "S-1", label: "S-1" },
    { value: "10-K", label: "10-K" },
    { value: "C", label: "Form C" },
    { value: "1-A", label: "Form 1-A" },
  ];

  const toggleFormType = (ft: string) => {
    setFormTypes(prev =>
      prev.includes(ft) ? prev.filter(t => t !== ft) : [...prev, ft]
    );
  };

  const toggleAll = () => {
    if (formTypes.length === FORM_OPTIONS.length) {
      setFormTypes([]);
    } else {
      setFormTypes(FORM_OPTIONS.map(o => o.value));
    }
  };

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const activeJob = await adminApi.getActiveEdgar(token);
      setJob(activeJob);
      if (activeJob?.id) {
        setElapsed(activeJob.elapsed_seconds || 0);

        if (tab === "startups") {
          const data = await adminApi.getEdgarStartups(token, activeJob.id);
          setStartups(data.items || []);
        } else if (tab === "filings") {
          const data = await adminApi.getEdgarFilings(token, activeJob.id);
          setFilings(data.items || []);
        }

        const logData = await adminApi.getEdgarLog(token, activeJob.id);
        setLog(logData.items || []);
      }
    } catch {
      // silent
    }
  }, [token, tab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const interval = job?.status === "running" ? 5000 : 30000;
    const timer = setInterval(fetchData, interval);
    return () => clearInterval(timer);
  }, [fetchData, job?.status]);

  useEffect(() => {
    if (job?.status !== "running") return;
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(timer);
  }, [job?.status]);

  async function handleStart(scanMode: string) {
    if (!token) return;
    setLoading(true);
    try {
      await adminApi.startEdgar(token, scanMode);
      await fetchData();
    } catch (e: any) {
      alert(e.message || "Failed to start EDGAR scan");
    }
    setLoading(false);
  }

  async function handlePause() {
    if (!token || !job) return;
    await adminApi.pauseEdgar(token, job.id);
    await fetchData();
  }

  async function handleResume() {
    if (!token || !job) return;
    await adminApi.resumeEdgar(token, job.id);
    await fetchData();
  }

  async function handleCancel() {
    if (!token || !job) return;
    if (!confirm("Cancel this EDGAR scan?")) return;
    await adminApi.cancelEdgar(token, job.id);
    await fetchData();
  }

  async function handleDiscover() {
    if (!token) return;
    setLoading(true);
    try {
      await adminApi.startEdgar(token, "discover", discoverDays, formTypes);
      await fetchData();
    } catch (e: any) {
      alert(e.message || "Failed to start discovery");
    }
    setLoading(false);
  }

  const summary = job?.progress_summary || {};
  const isActive = job?.status === "running" || job?.status === "paused";
  const canStart = !isActive && job?.status !== "pending";
  const matchRate = summary.startups_scanned > 0
    ? Math.round((summary.ciks_matched / summary.startups_scanned) * 100)
    : 0;

  return (
    <>
    <Sidebar />
    <div className="ml-56 p-8">
      <h1 className="font-serif text-2xl text-text-primary mb-6">EDGAR SEC Filings</h1>

      {/* Control Bar */}
      {/* Active job controls */}
      <div className="rounded border border-border bg-surface p-5 mb-6">
        <div className="flex items-center gap-3 mb-4">
          {canStart && (
            <>
              <button
                onClick={() => handleStart("full")}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
              >
                Run EDGAR Scan
              </button>
              <button
                onClick={() => handleStart("new_only")}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium rounded border border-accent text-accent hover:bg-accent/5 disabled:opacity-50 transition"
              >
                Scan New Only
              </button>
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
          {job?.current_phase && job.status === "running" && (
            <span className="text-xs text-text-tertiary">{PHASE_LABELS[job.current_phase] || job.current_phase}</span>
          )}
          {job?.error && <span className="text-xs text-red-600 ml-2">{job.error}</span>}
          {isActive && (
            <span className="text-xs text-text-tertiary ml-auto tabular-nums">{formatElapsed(elapsed)}</span>
          )}
        </div>

        {job && (
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            {job.scan_mode === "discover" ? (
              <>
                <div>
                  <p className="text-xs text-text-tertiary">Filings Discovered</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.filings_discovered || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Companies Extracted</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.companies_extracted || 0} / {summary.extract_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Duplicates Skipped</p>
                  <p className="text-sm font-medium text-text-tertiary tabular-nums">
                    {summary.duplicates_skipped || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Startups Created</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">
                    {summary.startups_created || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Enriched</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">
                    {summary.enrichments_completed || 0} / {summary.enrich_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Enrich Failed</p>
                  <p className="text-sm font-medium text-red-600 tabular-nums">
                    {summary.enrichments_failed || 0}
                  </p>
                </div>
              </>
            ) : (
              <>
                <div>
                  <p className="text-xs text-text-tertiary">Startups Scanned</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.startups_scanned || 0} / {summary.startups_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">CIKs Matched</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.ciks_matched || 0}
                    {summary.startups_scanned > 0 && (
                      <span className="text-text-tertiary text-xs ml-1">({matchRate}%)</span>
                    )}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Filings Found</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">{summary.filings_found || 0}</p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Filings Processed</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.filings_processed || 0} / {summary.filings_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Rounds Updated</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">
                    {(summary.rounds_updated || 0) + (summary.rounds_created || 0)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Valuations Added</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">{summary.valuations_added || 0}</p>
                </div>
              </>
            )}
          </div>
        )}

        {job?.progress_summary?.form_types && (
          <div className="flex gap-1.5 mt-2">
            {job.progress_summary.form_types.map((ft: string) => (
              <span key={ft} className="px-2 py-0.5 text-xs rounded bg-zinc-700 text-zinc-300">
                {ft}
              </span>
            ))}
          </div>
        )}

        {job && summary.current_startup && (
          <p className="text-xs text-text-tertiary mt-3">
            Currently: {summary.current_startup}
            {summary.current_filing && ` / ${summary.current_filing}`}
          </p>
        )}
      </div>

      {/* Discover section — always visible */}
      <div className="rounded border border-border bg-surface p-5 mb-6">
        <h3 className="text-sm font-medium text-text-primary mb-3">Discover New Companies from SEC Filings</h3>
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={handleDiscover}
            disabled={loading || isActive}
            className="px-4 py-2 text-sm font-medium rounded bg-score-high text-white hover:opacity-90 disabled:opacity-50 transition"
          >
            Discover New
          </button>
          <div className="flex items-center gap-1.5">
            <input
              type="number"
              value={discoverDays}
              onChange={(e) => setDiscoverDays(Math.max(1, parseInt(e.target.value) || 365))}
              className="w-16 px-2 py-1.5 text-sm rounded border border-border bg-background text-text-primary text-center tabular-nums"
              min={1}
              max={3650}
            />
            <span className="text-xs text-text-tertiary">days</span>
          </div>
          {isActive && (
            <span className="text-xs text-text-tertiary">Cancel current job to start a new discovery</span>
          )}
        </div>
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-text-secondary">Form Types</span>
            <button
              onClick={toggleAll}
              className="text-xs text-accent hover:text-accent-hover"
            >
              {formTypes.length === FORM_OPTIONS.length ? "None" : "All"}
            </button>
          </div>
          <div className="flex flex-wrap gap-3">
            {FORM_OPTIONS.map(opt => (
              <label key={opt.value} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formTypes.includes(opt.value)}
                  onChange={() => toggleFormType(opt.value)}
                  className="rounded border-border bg-background text-accent focus:ring-accent/20"
                />
                <span className="text-sm text-text-primary">{opt.label}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {job && (
        <>
          <div className="flex items-center gap-1 mb-4 border-b border-border">
            {(["startups", "filings"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
                  tab === t
                    ? "border-accent text-accent"
                    : "border-transparent text-text-tertiary hover:text-text-secondary"
                }`}
              >
                {t === "startups" ? "Startups" : "Filings"}
              </button>
            ))}
          </div>

          <div className="rounded border border-border bg-surface overflow-x-auto mb-6">
            {tab === "startups" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Startup</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">CIK</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Filings</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {startups.map((s, i) => (
                    <tr
                      key={i}
                      className={`border-b border-border last:border-b-0 ${
                        s.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"
                      }`}
                    >
                      <td className="px-4 py-2 text-text-primary font-medium">{s.startup_name}</td>
                      <td className="px-4 py-2 text-text-secondary tabular-nums">
                        {s.cik || <span className="text-text-tertiary">{s.status === "completed" ? "No match" : "\u2014"}</span>}
                      </td>
                      <td className="px-4 py-2 text-right text-text-secondary tabular-nums">
                        {s.filings_found > 0 ? s.filings_found : "\u2014"}
                      </td>
                      <td className="px-4 py-2"><Badge status={s.status} /></td>
                    </tr>
                  ))}
                  {startups.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">No startups scanned yet</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {tab === "filings" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Startup</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Filing</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Date</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Result</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filings.map((f, i) => (
                    <tr
                      key={i}
                      className={`border-b border-border last:border-b-0 ${
                        f.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"
                      }`}
                    >
                      <td className="px-4 py-2 text-text-primary font-medium">{f.startup_name}</td>
                      <td className="px-4 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          f.filing_type?.startsWith("D") ? "bg-blue-100 text-blue-800" :
                          f.filing_type?.startsWith("S") ? "bg-purple-100 text-purple-800" :
                          "bg-amber-100 text-amber-800"
                        }`}>
                          {f.filing_type}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-text-secondary tabular-nums">{f.filing_date}</td>
                      <td className="px-4 py-2 text-text-secondary text-xs">
                        {f.status === "completed" ? (
                          <>
                            {f.action === "created" && <span className="text-score-high">New round</span>}
                            {f.action === "updated" && <span className="text-blue-600">Updated</span>}
                            {f.action === "skipped" && <span className="text-text-tertiary">Skipped</span>}
                            {f.rounds_extracted != null && <span>{f.rounds_extracted} rounds</span>}
                            {f.amount && <span className="ml-1">({f.amount})</span>}
                            {f.valuation_added && <span className="ml-1 text-score-high">[+val]</span>}
                          </>
                        ) : f.error ? (
                          <span className="text-red-600" title={f.error}>Error</span>
                        ) : "\u2014"}
                      </td>
                      <td className="px-4 py-2"><Badge status={f.status} /></td>
                    </tr>
                  ))}
                  {filings.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-text-tertiary text-sm">No filings processed yet</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </div>

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
          No EDGAR scans yet. Run a scan to match startups with SEC filings and extract funding data.
        </div>
      )}
    </div>
    </>
  );
}
