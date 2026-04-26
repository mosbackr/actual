"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { AccessDenied } from "@/components/AccessDenied";
import type { MarketingJob } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700",
  running: "bg-blue-100 text-blue-700",
  paused: "bg-gray-100 text-gray-600",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

function previewHtml(html: string): string {
  return html
    .replace(/\{\{score\}\}/g, "85")
    .replace(/\{\{cta_url\}\}/g, "https://www.deepthesis.org/score/example");
}

export default function MarketingPage() {
  const { data: session, status } = useSession();
  const token = (session as any)?.backendToken;

  // Composer state
  const [subject, setSubject] = useState("");
  const [prompt, setPrompt] = useState("");
  const [generatedHtml, setGeneratedHtml] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Send state
  const [sending, setSending] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // Jobs state
  const [jobs, setJobs] = useState<MarketingJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);

  const iframeRef = useRef<HTMLIFrameElement>(null);

  const fetchJobs = useCallback(async () => {
    if (!token) return;
    try {
      const data = await adminApi.getMarketingJobs(token);
      setJobs(data);
    } catch (e) {
      console.error("Failed to load marketing jobs", e);
    }
    setJobsLoading(false);
  }, [token]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Poll running jobs every 5 seconds
  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === "running" || j.status === "paused");
    if (!hasActive) return;
    const interval = setInterval(() => {
      fetchJobs();
    }, 5000);
    return () => clearInterval(interval);
  }, [jobs, fetchJobs]);

  // Update iframe when HTML changes
  useEffect(() => {
    if (!iframeRef.current || !generatedHtml) return;
    const doc = iframeRef.current.contentDocument;
    if (doc) {
      doc.open();
      doc.write(previewHtml(generatedHtml));
      doc.close();
    }
  }, [generatedHtml]);

  async function handleGenerate() {
    if (!token || !prompt.trim()) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const result = await adminApi.generateMarketingEmail(token, prompt);
      setGeneratedHtml(result.html);
    } catch (e: any) {
      setGenerateError(e.message || "Failed to generate email");
    }
    setGenerating(false);
  }

  async function handleSend() {
    if (!token || !subject.trim() || !generatedHtml.trim()) return;
    setSending(true);
    try {
      await adminApi.startMarketingSend(token, subject, generatedHtml);
      setShowConfirm(false);
      await fetchJobs();
    } catch (e: any) {
      alert(e.message || "Failed to start send");
    }
    setSending(false);
  }

  async function handlePause(jobId: string) {
    if (!token) return;
    try {
      await adminApi.pauseMarketingJob(token, jobId);
      await fetchJobs();
    } catch (e: any) {
      alert(e.message || "Failed to pause job");
    }
  }

  async function handleResume(jobId: string) {
    if (!token) return;
    try {
      await adminApi.resumeMarketingJob(token, jobId);
      await fetchJobs();
    } catch (e: any) {
      alert(e.message || "Failed to resume job");
    }
  }

  if (status === "loading") return null;
  if (!session || (session as any).role !== "superadmin") return <AccessDenied />;

  const activeJobs = jobs.filter((j) => j.status === "running" || j.status === "paused");

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h1 className="text-2xl font-semibold text-text-primary mb-6">Marketing Emails</h1>

        {/* Two-panel layout */}
        <div className="grid grid-cols-2 gap-6 mb-6">
          {/* Left: Email Composer */}
          <div className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-lg font-medium text-text-primary mb-4">Email Composer</h2>

            <label className="block text-sm text-text-secondary mb-1">Subject Line</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Your Startup Score is Ready"
              className="w-full px-3 py-2 border border-border rounded bg-background text-text-primary text-sm placeholder:text-text-tertiary focus:outline-none focus:border-accent mb-4"
            />

            <label className="block text-sm text-text-secondary mb-1">Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the email you want to generate..."
              rows={6}
              className="w-full px-3 py-2 border border-border rounded bg-background text-text-primary text-sm placeholder:text-text-tertiary focus:outline-none focus:border-accent resize-none mb-4"
            />

            <button
              onClick={handleGenerate}
              disabled={generating || !prompt.trim()}
              className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
            >
              {generating ? "Generating..." : "Generate"}
            </button>

            {generateError && (
              <p className="text-xs text-red-500 mt-2">{generateError}</p>
            )}
          </div>

          {/* Right: Preview */}
          <div className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-lg font-medium text-text-primary mb-4">Preview</h2>
            {generatedHtml ? (
              <iframe
                ref={iframeRef}
                sandbox=""
                title="Email Preview"
                className="w-full h-[400px] border border-border rounded bg-white"
              />
            ) : (
              <div className="w-full h-[400px] border border-border rounded bg-background flex items-center justify-center">
                <p className="text-text-tertiary text-sm">
                  Generated email preview will appear here
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Send controls */}
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-text-primary">Send Campaign</h2>
              <p className="text-xs text-text-tertiary mt-0.5">
                Send the generated email to all scored investors
              </p>
            </div>
            <button
              onClick={() => setShowConfirm(true)}
              disabled={!generatedHtml.trim() || !subject.trim() || sending}
              className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
            >
              Send to All Scored Investors
            </button>
          </div>
        </div>

        {/* Confirmation dialog */}
        {showConfirm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-surface border border-border rounded-lg p-6 max-w-md w-full mx-4">
              <h3 className="text-lg font-medium text-text-primary mb-2">Confirm Send</h3>
              <p className="text-sm text-text-secondary mb-4">
                Are you sure you want to send this email to all scored investors? Subject: <strong>{subject}</strong>
              </p>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setShowConfirm(false)}
                  className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSend}
                  disabled={sending}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  {sending ? "Starting..." : "Confirm Send"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Active job progress */}
        {activeJobs.map((job) => {
          const progressPct =
            job.total_recipients > 0
              ? Math.round((job.sent_count / job.total_recipients) * 100)
              : 0;
          const isRunning = job.status === "running";
          const isPaused = job.status === "paused";

          return (
            <div key={job.id} className="border border-border rounded-lg p-4 mb-4 bg-surface">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-medium text-text-primary">{job.subject}</h2>
                  <p className="text-xs text-text-tertiary mt-0.5">
                    {job.sent_count} sent, {job.failed_count} failed of {job.total_recipients} total
                    {job.current_investor_name && isRunning && (
                      <> &mdash; sending to <strong>{job.current_investor_name}</strong></>
                    )}
                    {isPaused && " \u2014 paused"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {isRunning && (
                    <button
                      onClick={() => handlePause(job.id)}
                      className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition"
                    >
                      Pause
                    </button>
                  )}
                  {isPaused && (
                    <button
                      onClick={() => handleResume(job.id)}
                      className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition"
                    >
                      Resume
                    </button>
                  )}
                </div>
              </div>
              <div className="mt-3">
                <div className="w-full bg-background rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${isPaused ? "bg-text-tertiary" : "bg-accent"}`}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}

        {/* Job history table */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="text-lg font-medium text-text-primary mb-4">Job History</h2>
          {jobsLoading ? (
            <p className="text-text-tertiary text-sm">Loading...</p>
          ) : jobs.length === 0 ? (
            <p className="text-text-tertiary text-sm">No marketing jobs yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Subject</th>
                    <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Status</th>
                    <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Sent</th>
                    <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Failed</th>
                    <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Total</th>
                    <th className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id} className="border-b border-border hover:bg-hover-row transition-colors">
                      <td className="px-3 py-4 text-text-primary">{job.subject}</td>
                      <td className="px-3 py-4">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[job.status] || "bg-gray-100 text-gray-700"}`}>
                          {job.status}
                        </span>
                      </td>
                      <td className="px-3 py-4 text-text-secondary">{job.sent_count}</td>
                      <td className="px-3 py-4 text-text-secondary">{job.failed_count}</td>
                      <td className="px-3 py-4 text-text-secondary">{job.total_recipients}</td>
                      <td className="px-3 py-4 text-text-tertiary whitespace-nowrap">
                        {job.created_at ? new Date(job.created_at).toLocaleDateString() : "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
