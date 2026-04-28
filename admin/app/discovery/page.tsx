"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { AccessDenied } from "@/components/AccessDenied";
import type {
  DiscoveredStartupItem,
  DiscoveryStatusResponse,
} from "@/lib/types";

const CLASSIFICATION_TABS = [
  { key: "all", label: "All" },
  { key: "startup", label: "Startups" },
  { key: "not_startup", label: "Not Startup" },
  { key: "uncertain", label: "Uncertain" },
  { key: "unclassified", label: "Unclassified" },
];

function classificationBadge(status: string) {
  switch (status) {
    case "startup":
      return "bg-green-500/10 text-green-400 border-green-500/20";
    case "not_startup":
      return "bg-red-500/10 text-red-400 border-red-500/20";
    case "uncertain":
      return "bg-yellow-500/10 text-yellow-400 border-yellow-500/20";
    default:
      return "bg-gray-500/10 text-gray-400 border-gray-500/20";
  }
}

export default function DiscoveryPage() {
  const { data: session, status: authStatus } = useSession();
  const token = session?.backendToken;

  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatusResponse | null>(null);
  const [startups, setStartups] = useState<DiscoveredStartupItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [classification, setClassification] = useState("all");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchStatus = useCallback(async () => {
    if (!token) return;
    try {
      const s = await adminApi.getDiscoveryStatus(token);
      setDiscoveryStatus(s);
    } catch {}
  }, [token]);

  const fetchStartups = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await adminApi.getDiscoveredStartups(token, {
        classification,
        q: search || undefined,
        page,
        per_page: 50,
      });
      setStartups(data.items);
      setTotal(data.total);
      setPages(data.pages);
    } catch {}
    setLoading(false);
  }, [token, classification, search, page]);

  useEffect(() => {
    fetchStatus();
    fetchStartups();
  }, [fetchStatus, fetchStartups]);

  // Poll while jobs are running
  useEffect(() => {
    const importRunning = discoveryStatus?.import_job?.status === "running";
    const pipelineRunning = discoveryStatus?.pipeline_job?.status === "running";
    if (!importRunning && !pipelineRunning) return;
    const interval = setInterval(() => {
      fetchStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [discoveryStatus?.import_job?.status, discoveryStatus?.pipeline_job?.status, fetchStatus]);

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !token) return;
    setBatchLoading(true);
    try {
      await adminApi.importDiscoveryCSV(token, file);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Import failed");
    }
    setBatchLoading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function startPipeline() {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.startDiscoveryPipeline(token);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Failed to start pipeline");
    }
    setBatchLoading(false);
  }

  async function pauseJob(jobId: string) {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.pauseDiscoveryBatch(token, jobId);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Failed to pause");
    }
    setBatchLoading(false);
  }

  async function resumeJob(jobId: string) {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.resumeDiscoveryBatch(token, jobId);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Failed to resume");
    }
    setBatchLoading(false);
  }

  async function handlePromote(id: string) {
    if (!token) return;
    try {
      await adminApi.promoteStartup(token, id);
      fetchStartups();
    } catch (err: any) {
      alert(err.message || "Failed to promote");
    }
  }

  async function handleReject(id: string) {
    if (!token) return;
    try {
      await adminApi.rejectStartup(token, id);
      fetchStartups();
    } catch (err: any) {
      alert(err.message || "Failed to reject");
    }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  }

  const importJob = discoveryStatus?.import_job;
  const pipelineJob = discoveryStatus?.pipeline_job;
  const stats = discoveryStatus?.stats;

  if (authStatus === "loading") return null;
  if (!session || (session as any).role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-text-primary">Startup Discovery</h1>
          <p className="text-sm text-text-secondary mt-1">
            Delaware C-corp filings → Founder enrichment → AI classification → Perplexity research
          </p>
        </div>

        {/* Stats Bar */}
        {stats && (
          <div className="grid grid-cols-4 gap-4 mb-6">
            {[
              { label: "Imported", value: stats.total_imported },
              { label: "Classified as Startup", value: stats.classified_startup },
              { label: "Enriched", value: stats.enriched },
              { label: "Promoted", value: stats.promoted },
            ].map((stat) => (
              <div key={stat.label} className="border border-border rounded-lg p-3 bg-surface">
                <p className="text-xs text-text-tertiary">{stat.label}</p>
                <p className="text-xl font-semibold text-text-primary mt-1">
                  {stat.value.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Batch Controls */}
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-text-primary">Pipeline Controls</h2>
              <p className="text-xs text-text-tertiary mt-0.5">
                Import Delaware CSVs, then run the classification + enrichment pipeline
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".csv"
                ref={fileInputRef}
                onChange={handleFileUpload}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={batchLoading || importJob?.status === "running"}
                className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition disabled:opacity-50"
              >
                Import CSV
              </button>

              {(!pipelineJob || !["running", "paused"].includes(pipelineJob.status)) && (
                <button
                  onClick={startPipeline}
                  disabled={batchLoading}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  Run Pipeline
                </button>
              )}

              {pipelineJob?.status === "running" && (
                <button
                  onClick={() => pauseJob(pipelineJob.id)}
                  disabled={batchLoading}
                  className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition disabled:opacity-50"
                >
                  Pause
                </button>
              )}

              {pipelineJob?.status === "paused" && (
                <button
                  onClick={() => resumeJob(pipelineJob.id)}
                  disabled={batchLoading}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  Resume
                </button>
              )}
            </div>
          </div>

          {/* Import progress */}
          {importJob && importJob.status === "running" && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
                <span>
                  Importing: {importJob.processed_items}/{importJob.total_items}
                  {importJob.current_item_name && (
                    <> — <strong>{importJob.current_item_name}</strong></>
                  )}
                </span>
                <span>{importJob.items_created.toLocaleString()} created</span>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className="h-2 rounded-full bg-accent transition-all"
                  style={{ width: `${importJob.total_items ? Math.round((importJob.processed_items / importJob.total_items) * 100) : 0}%` }}
                />
              </div>
            </div>
          )}

          {/* Pipeline progress */}
          {pipelineJob && ["running", "paused"].includes(pipelineJob.status) && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
                <span>
                  Pipeline: {pipelineJob.processed_items}/{pipelineJob.total_items}
                  {pipelineJob.current_item_name && pipelineJob.status === "running" && (
                    <> — <strong>{pipelineJob.current_item_name}</strong></>
                  )}
                  {pipelineJob.status === "paused" && " — paused"}
                </span>
                <span>{pipelineJob.items_created.toLocaleString()} startups found</span>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${pipelineJob.status === "paused" ? "bg-text-tertiary" : "bg-accent"}`}
                  style={{ width: `${pipelineJob.total_items ? Math.round((pipelineJob.processed_items / pipelineJob.total_items) * 100) : 0}%` }}
                />
              </div>
            </div>
          )}

          {pipelineJob?.status === "completed" && (
            <p className="text-xs text-text-tertiary mt-2">
              Pipeline complete — {pipelineJob.items_created.toLocaleString()} startups identified
              out of {pipelineJob.total_items.toLocaleString()} processed
            </p>
          )}
        </div>

        {/* Classification Tabs */}
        <div className="flex gap-1 mb-4">
          {CLASSIFICATION_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => { setClassification(tab.key); setPage(1); }}
              className={`px-3 py-1.5 text-sm rounded transition ${
                classification === tab.key
                  ? "bg-accent text-white"
                  : "text-text-secondary hover:text-text-primary hover:bg-hover-row"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Search company name..."
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
              onClick={() => { setSearchInput(""); setSearch(""); setPage(1); }}
              className="px-3 py-2 text-xs text-text-tertiary hover:text-text-secondary transition"
            >
              Clear
            </button>
          )}
        </form>

        {/* Results */}
        {loading ? (
          <p className="text-text-tertiary text-sm py-10 text-center">Loading...</p>
        ) : (
          <>
            <p className="text-xs text-text-tertiary mb-3">{total.toLocaleString()} results</p>
            <div className="space-y-2">
              {startups.map((s) => (
                <div key={s.id} className="border border-border rounded-lg bg-surface">
                  <div
                    className="flex items-center justify-between p-3 cursor-pointer hover:bg-hover-row transition"
                    onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-text-primary text-sm truncate">
                          {s.name}
                        </span>
                        {s.delaware_corp_name && s.delaware_corp_name !== s.name && (
                          <span className="text-xs text-text-tertiary truncate">
                            (filed as: {s.delaware_corp_name})
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-text-tertiary">
                        {s.delaware_filed_at && (
                          <span>Filed: {new Date(s.delaware_filed_at).toLocaleDateString()}</span>
                        )}
                        <span>{s.founders.length} founder{s.founders.length !== 1 ? "s" : ""}</span>
                        {s.location_city && <span>{s.location_city}, {s.location_state}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <span
                        className={`px-2 py-0.5 text-xs rounded border ${classificationBadge(s.classification_status)}`}
                      >
                        {s.classification_status}
                      </span>
                      {s.enrichment_status === "complete" && (
                        <span className="px-2 py-0.5 text-xs rounded border bg-blue-500/10 text-blue-400 border-blue-500/20">
                          enriched
                        </span>
                      )}
                      {s.status === "approved" && (
                        <span className="px-2 py-0.5 text-xs rounded border bg-green-500/10 text-green-400 border-green-500/20">
                          promoted
                        </span>
                      )}
                    </div>
                  </div>

                  {expandedId === s.id && (
                    <div className="border-t border-border p-4">
                      {/* Actions */}
                      <div className="flex gap-2 mb-4">
                        {s.status !== "approved" && s.classification_status === "startup" && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handlePromote(s.id); }}
                            className="px-3 py-1 text-xs bg-accent text-white rounded hover:bg-accent/90 transition"
                          >
                            Promote to Approved
                          </button>
                        )}
                        {s.classification_status !== "not_startup" && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleReject(s.id); }}
                            className="px-3 py-1 text-xs border border-border text-text-secondary rounded hover:border-red-500 hover:text-red-400 transition"
                          >
                            Reject
                          </button>
                        )}
                      </div>

                      {/* Classification reasoning */}
                      {s.classification_metadata?.reasoning && (
                        <div className="mb-4">
                          <h4 className="text-xs font-medium text-text-secondary mb-1">Classification Reasoning</h4>
                          <p className="text-sm text-text-primary leading-relaxed">
                            {s.classification_metadata.reasoning}
                          </p>
                          {s.classification_metadata.confidence !== undefined && (
                            <p className="text-xs text-text-tertiary mt-1">
                              Confidence: {Math.round(s.classification_metadata.confidence * 100)}%
                            </p>
                          )}
                        </div>
                      )}

                      {/* Company details (if enriched) */}
                      {s.enrichment_status === "complete" && s.description && (
                        <div className="mb-4">
                          <h4 className="text-xs font-medium text-text-secondary mb-1">Company Details</h4>
                          <p className="text-sm text-text-primary">{s.description}</p>
                          <div className="flex gap-4 mt-2 text-xs text-text-tertiary">
                            {s.stage && <span>Stage: {s.stage}</span>}
                            {s.total_funding && <span>Funding: {s.total_funding}</span>}
                            {s.employee_count && <span>Team: {s.employee_count}</span>}
                            {s.website_url && (
                              <a href={s.website_url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                                Website
                              </a>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Founders */}
                      {s.founders.length > 0 && (
                        <div>
                          <h4 className="text-xs font-medium text-text-secondary mb-2">Founders</h4>
                          <div className="space-y-3">
                            {s.founders.map((f) => (
                              <div key={f.id} className="border border-border rounded p-3 bg-background">
                                <div className="flex items-center gap-3">
                                  {f.profile_photo_url && (
                                    <img
                                      src={f.profile_photo_url}
                                      alt={f.name}
                                      className="w-10 h-10 rounded-full object-cover"
                                    />
                                  )}
                                  <div>
                                    <div className="flex items-center gap-2">
                                      <span className="font-medium text-sm text-text-primary">{f.name}</span>
                                      {f.linkedin_url && (
                                        <a
                                          href={f.linkedin_url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-xs text-accent hover:underline"
                                        >
                                          LinkedIn
                                        </a>
                                      )}
                                    </div>
                                    {f.headline && (
                                      <p className="text-xs text-text-tertiary">{f.headline}</p>
                                    )}
                                    {f.location && (
                                      <p className="text-xs text-text-tertiary">{f.location}</p>
                                    )}
                                  </div>
                                </div>

                                {f.work_history && f.work_history.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-xs text-text-secondary font-medium mb-1">Work History</p>
                                    {f.work_history.slice(0, 3).map((job, i) => (
                                      <p key={i} className="text-xs text-text-tertiary">
                                        {job.title} at {job.company}
                                      </p>
                                    ))}
                                  </div>
                                )}

                                {f.education_history && f.education_history.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-xs text-text-secondary font-medium mb-1">Education</p>
                                    {f.education_history.slice(0, 2).map((edu, i) => (
                                      <p key={i} className="text-xs text-text-tertiary">
                                        {edu.degree} {edu.field ? `in ${edu.field}` : ""} — {edu.school}
                                      </p>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {startups.length === 0 && (
                <p className="text-center text-text-tertiary py-8">
                  No discovered startups yet. Import a Delaware CSV to get started.
                </p>
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
