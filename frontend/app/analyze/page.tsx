"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

const ALLOWED_EXTENSIONS = ["pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv", "md", "txt"];
const MAX_FILE_SIZE = 20 * 1024 * 1024;
const MAX_TOTAL_SIZE = 50 * 1024 * 1024;
const MAX_FILES = 10;

export default function AnalyzePage() {
  const { data: session, status: sessionStatus } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();

  const [files, setFiles] = useState<File[]>([]);
  const [companyName, setCompanyName] = useState("");
  const [publishConsent, setPublishConsent] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const validateFile = (file: File): string | null => {
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!ALLOWED_EXTENSIONS.includes(ext)) return `Unsupported file type: .${ext}`;
    if (file.size > MAX_FILE_SIZE) return `${file.name} exceeds 20MB limit`;
    return null;
  };

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles);
    const errors: string[] = [];
    const valid: File[] = [];

    for (const f of arr) {
      const err = validateFile(f);
      if (err) errors.push(err);
      else valid.push(f);
    }

    setFiles((prev) => {
      const combined = [...prev, ...valid];
      if (combined.length > MAX_FILES) {
        errors.push(`Maximum ${MAX_FILES} files allowed`);
        return prev;
      }
      const totalSize = combined.reduce((s, f) => s + f.size, 0);
      if (totalSize > MAX_TOTAL_SIZE) {
        errors.push("Total size exceeds 50MB limit");
        return prev;
      }
      return combined;
    });

    if (errors.length) setError(errors.join(". "));
    else setError(null);
  }, []);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setError(null);
  };

  const handleSubmit = async () => {
    if (!token || !companyName.trim() || files.length === 0) return;
    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("company_name", companyName.trim());
      formData.append("publish_consent", String(publishConsent));
      for (const f of files) {
        formData.append("files", f);
      }
      const result = await api.createAnalysis(token, formData);
      router.push(`/analyze/${result.id}`);
    } catch (e: any) {
      setError(e.message || "Upload failed");
      setUploading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
    return `${(bytes / 1e3).toFixed(0)} KB`;
  };

  // Not logged in
  if (sessionStatus === "loading") {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center text-text-tertiary">Loading...</div>
    );
  }

  if (!session) {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center">
        <h1 className="font-serif text-3xl text-text-primary mb-4">Free Pitch Analysis</h1>
        <p className="text-text-secondary mb-2">
          Upload your pitch deck and documents. Our AI evaluates your startup across 8 critical
          factors and produces detailed reports with fundraising projections.
        </p>
        <p className="text-text-tertiary text-sm mb-8">First analysis is free. No credit card required.</p>
        <div className="flex gap-3 justify-center">
          <Link
            href="/auth/signup"
            className="px-6 py-2.5 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            Sign Up
          </Link>
          <Link
            href="/auth/signin"
            className="px-6 py-2.5 text-sm font-medium rounded border border-accent text-accent hover:bg-accent/5 transition"
          >
            Sign In
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-serif text-2xl text-text-primary">Analyze Your Pitch</h1>
        <Link href="/analyze/history" className="text-sm text-accent hover:text-accent-hover transition">
          View History
        </Link>
      </div>

      {/* Company name */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-text-primary mb-1.5">Company Name</label>
        <input
          type="text"
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          placeholder="e.g. Acme Corp"
          className="w-full px-3 py-2 text-sm rounded border border-border bg-surface text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent"
        />
      </div>

      {/* Drop zone */}
      <div
        className={`rounded border-2 border-dashed p-8 text-center transition cursor-pointer ${
          dragOver ? "border-accent bg-accent/5" : "border-border bg-surface hover:border-accent/50"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files); }}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <input
          id="file-input"
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.map((e) => `.${e}`).join(",")}
          className="hidden"
          onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
        />
        <p className="text-text-secondary text-sm mb-1">Drop files here or click to browse</p>
        <p className="text-text-tertiary text-xs">
          PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, CSV, MD, TXT — max 10 files, 20MB each
        </p>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {files.map((f, i) => (
            <div key={i} className="flex items-center justify-between px-3 py-2 rounded border border-border bg-surface text-sm">
              <div className="flex items-center gap-2 min-w-0">
                <span className="px-1.5 py-0.5 text-xs rounded bg-accent/10 text-accent font-medium uppercase">
                  {f.name.split(".").pop()}
                </span>
                <span className="text-text-primary truncate">{f.name}</span>
                <span className="text-text-tertiary text-xs">{formatSize(f.size)}</span>
              </div>
              <button onClick={() => removeFile(i)} className="text-text-tertiary hover:text-red-500 text-xs ml-2">
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Publish consent */}
      <label className="flex items-start gap-2.5 mt-4 cursor-pointer">
        <input
          type="checkbox"
          checked={publishConsent}
          onChange={(e) => setPublishConsent(e.target.checked)}
          className="mt-0.5 rounded border-border bg-surface text-accent focus:ring-accent/20"
        />
        <span className="text-xs text-text-secondary leading-relaxed">
          Allow Deep Thesis to display your company on our public startup directory. Only your
          company name, industry, stage, and description are shown — reports, documents, and scores
          remain private.
        </span>
      </label>

      {/* Error */}
      {error && (
        <div className="mt-3 px-3 py-2 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={uploading || !companyName.trim() || files.length === 0}
        className="mt-5 w-full py-2.5 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
      >
        {uploading ? "Uploading..." : "Analyze My Pitch"}
      </button>
    </div>
  );
}
