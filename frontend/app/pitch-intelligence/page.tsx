"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PitchSessionSummary } from "@/lib/types";

export default function PitchIntelligencePage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <PitchIntelligenceContent />
    </Suspense>
  );
}

const ACCEPTED_TYPES: Record<string, string> = {
  "audio/mpeg": ".mp3",
  "audio/wav": ".wav",
  "audio/x-wav": ".wav",
  "audio/mp4": ".m4a",
  "audio/x-m4a": ".m4a",
  "video/mp4": ".mp4",
  "video/webm": ".webm",
  "audio/webm": ".webm",
};

function PitchIntelligenceContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();

  const [sessions, setSessions] = useState<PitchSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [title, setTitle] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"upload" | "transcript">("upload");
  const [transcriptText, setTranscriptText] = useState("");
  const [submittingTranscript, setSubmittingTranscript] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSessions = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listPitchSessions(token);
      setSessions(data.items);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleUpload = async (file: File) => {
    if (!token) return;
    if (!ACCEPTED_TYPES[file.type]) {
      setError("Unsupported file type. Please upload MP3, WAV, M4A, MP4, or WebM.");
      return;
    }
    if (file.size > 500 * 1024 * 1024) {
      setError("File too large. Maximum size is 500MB.");
      return;
    }

    setError(null);
    setUploading(true);
    setUploadProgress(0);

    try {
      // 1. Get presigned URL
      const { id, upload_url } = await api.createPitchUpload(
        token,
        file.name,
        file.type,
        title || undefined,
      );

      // 2. Upload directly to S3
      setUploadProgress(10);
      const xhr = new XMLHttpRequest();
      await new Promise<void>((resolve, reject) => {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            setUploadProgress(10 + Math.round((e.loaded / e.total) * 80));
          }
        };
        xhr.onload = () => (xhr.status < 400 ? resolve() : reject(new Error(`Upload failed: ${xhr.status}`)));
        xhr.onerror = () => reject(new Error("Upload failed"));
        xhr.open("PUT", upload_url);
        xhr.setRequestHeader("Content-Type", file.type);
        xhr.send(file);
      });

      // 3. Notify backend
      setUploadProgress(95);
      await api.completePitchUpload(token, id);
      setUploadProgress(100);

      // Navigate to session page
      router.push(`/pitch-intelligence/${id}`);
    } catch (e: any) {
      setError(e.message || "Upload failed");
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
  };

  const handleTranscriptSubmit = async () => {
    if (!token) return;
    if (transcriptText.trim().length < 50) {
      setError("Transcript is too short. Please paste at least a few lines of conversation.");
      return;
    }
    setError(null);
    setSubmittingTranscript(true);
    try {
      const result = await api.submitPitchTranscript(token, transcriptText, title || undefined);
      router.push(`/pitch-intelligence/${result.id}`);
    } catch (e: any) {
      setError(e.message || "Failed to submit transcript");
      setSubmittingTranscript(false);
    }
  };

  const statusLabel = (status: string) => {
    const map: Record<string, { text: string; color: string }> = {
      uploading: { text: "Uploading", color: "text-yellow-600" },
      transcribing: { text: "Transcribing", color: "text-blue-600" },
      labeling: { text: "Needs Speaker Labels", color: "text-orange-600" },
      analyzing: { text: "Analyzing", color: "text-blue-600" },
      complete: { text: "Complete", color: "text-green-600" },
      failed: { text: "Failed", color: "text-red-600" },
    };
    const info = map[status] || { text: status, color: "text-text-secondary" };
    return <span className={info.color}>{info.text}</span>;
  };

  if (!session) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <p className="text-text-secondary">Sign in to access Pitch Intelligence.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-serif text-text-primary mb-2">Pitch Intelligence</h1>
        <p className="text-text-secondary">
          Upload a pitch recording or paste a transcript to get AI-powered analysis, fact-checking, and coaching.
        </p>
      </div>

      {/* Mode Toggle + Input */}
      {!uploading && !submittingTranscript && (
        <div className="mb-8">
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setMode("upload")}
              className={`px-4 py-2 text-sm rounded-lg border transition ${
                mode === "upload"
                  ? "bg-accent text-white border-accent"
                  : "bg-surface text-text-secondary border-border hover:border-accent/50"
              }`}
            >
              Upload Recording
            </button>
            <button
              onClick={() => setMode("transcript")}
              className={`px-4 py-2 text-sm rounded-lg border transition ${
                mode === "transcript"
                  ? "bg-accent text-white border-accent"
                  : "bg-surface text-text-secondary border-border hover:border-accent/50"
              }`}
            >
              Paste Transcript
            </button>
          </div>
          <div className="mb-4">
            <input
              type="text"
              placeholder="Session title (optional)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
            />
          </div>

          {mode === "upload" ? (
            <div
              className={`relative rounded-lg border-2 border-dashed p-12 text-center transition cursor-pointer ${
                dragOver
                  ? "border-accent bg-accent/5"
                  : "border-border hover:border-accent/50"
              }`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".mp3,.wav,.m4a,.mp4,.webm"
                className="hidden"
                onChange={handleFileSelect}
              />
              <div className="text-4xl mb-3 text-text-tertiary">&#127908;</div>
              <p className="text-text-primary font-medium mb-1">
                Drop an audio or video file here, or click to browse
              </p>
              <p className="text-text-tertiary text-sm">
                MP3, WAV, M4A, MP4, WebM — up to 500MB
              </p>
            </div>
          ) : (
            <div>
              <textarea
                value={transcriptText}
                onChange={(e) => setTranscriptText(e.target.value)}
                placeholder={"Paste your transcript here...\n\nSupported formats:\n  Speaker Name: What they said...\n  00:01:23 Speaker Name (Zoom format)\n  Or just plain text"}
                className="w-full h-64 rounded-lg border border-border bg-surface px-4 py-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none resize-y font-mono"
              />
              <div className="flex items-center justify-between mt-3">
                <p className="text-xs text-text-tertiary">
                  {transcriptText.length > 0
                    ? `${transcriptText.length.toLocaleString()} characters`
                    : "Min 50 characters"}
                </p>
                <button
                  onClick={handleTranscriptSubmit}
                  disabled={transcriptText.trim().length < 50}
                  className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Analyze Transcript
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Upload Progress */}
      {uploading && (
        <div className="mb-8 rounded-lg border border-border bg-surface p-6">
          <p className="text-sm text-text-secondary mb-3">Uploading...</p>
          <div className="h-2 rounded-full bg-surface-alt overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-xs text-text-tertiary mt-2">{uploadProgress}%</p>
        </div>
      )}

      {error && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Session List */}
      <div>
        <h2 className="text-lg font-medium text-text-primary mb-4">Your Pitch Sessions</h2>
        {loading ? (
          <p className="text-text-tertiary text-sm">Loading...</p>
        ) : sessions.length === 0 ? (
          <p className="text-text-tertiary text-sm">No pitch sessions yet. Upload your first recording above.</p>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <Link
                key={s.id}
                href={`/pitch-intelligence/${s.id}`}
                className="block rounded-lg border border-border bg-surface p-4 hover:border-accent/50 transition"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-text-primary">
                      {s.title || "Untitled Pitch"}
                    </p>
                    <p className="text-sm text-text-tertiary mt-0.5">
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : ""}
                      {s.file_duration_seconds
                        ? ` · ${Math.round(s.file_duration_seconds / 60)}min`
                        : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    {s.scores?.overall != null && (
                      <span className="text-lg font-medium text-accent">{s.scores.overall}</span>
                    )}
                    <span className="text-sm">{statusLabel(s.status)}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
