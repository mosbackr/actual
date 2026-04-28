"use client";

import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, DataroomDocument, DataroomFounderView } from "@/lib/api";

const SECTIONS: { key: string; title: string; description: string }[] = [
  {
    key: "corporate",
    title: "Corporate Documents",
    description:
      "Certificate of Incorporation, Bylaws, Cap Table, Operating Agreement",
  },
  {
    key: "financials",
    title: "Financials",
    description:
      "P&L, Balance Sheet, Cash Flow, Projections, Bank Statements",
  },
  {
    key: "fundraising",
    title: "Fundraising",
    description: "Pitch Deck, Executive Summary, Term Sheet, Use of Funds",
  },
  {
    key: "product",
    title: "Product",
    description: "Demo, Screenshots, Technical Architecture, Roadmap",
  },
  {
    key: "legal",
    title: "Legal",
    description:
      "IP Assignments, Material Contracts, Employment Agreements, Compliance",
  },
  {
    key: "team",
    title: "Team",
    description:
      "Org Chart, Key Bios, Advisory Board, Compensation Summary",
  },
];

const ACCEPTED_TYPES =
  ".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.gif,.webp,.md,.txt";

/* ------------------------------------------------------------------ */
/*  DropZone                                                           */
/* ------------------------------------------------------------------ */

function DropZone({
  sectionKey,
  documents,
  onUpload,
  onRemove,
  uploading,
}: {
  sectionKey: string;
  documents: DataroomDocument[];
  onUpload: (files: FileList) => void;
  onRemove: (docId: string) => void;
  uploading: boolean;
}) {
  const [dragOver, setDragOver] = useState(false);

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onUpload(e.dataTransfer.files);
    }
  }

  function handleClick() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ACCEPTED_TYPES;
    input.multiple = true;
    input.onchange = () => {
      if (input.files && input.files.length > 0) {
        onUpload(input.files);
      }
    };
    input.click();
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return (
    <div>
      {/* Drop area */}
      <div
        role="button"
        tabIndex={0}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") handleClick();
        }}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition ${
          dragOver
            ? "border-accent bg-accent/5"
            : "border-border hover:border-accent/50"
        }`}
      >
        {uploading ? (
          <p className="text-sm text-text-tertiary">Uploading...</p>
        ) : (
          <>
            <p className="text-sm text-text-secondary">
              Drag &amp; drop files here, or{" "}
              <span className="text-accent font-medium">browse</span>
            </p>
            <p className="text-xs text-text-tertiary mt-1">
              PDF, DOCX, PPTX, XLSX, CSV, images, Markdown, TXT
            </p>
          </>
        )}
      </div>

      {/* Uploaded files list */}
      {documents.length > 0 && (
        <ul className="mt-3 space-y-1">
          {documents.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center justify-between rounded bg-bg-secondary px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-text-primary truncate">
                  {doc.original_filename}
                </span>
                <span className="text-text-tertiary text-xs whitespace-nowrap">
                  {formatSize(doc.file_size_bytes)}
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(doc.id);
                }}
                className="text-xs text-score-low hover:text-score-low/80 ml-2 whitespace-nowrap"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function DataroomUploadPage() {
  const { data: session, status: sessionStatus } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const shareToken = params.token as string;
  const router = useRouter();

  const [dataroom, setDataroom] = useState<DataroomFounderView | null>(null);
  const [documents, setDocuments] = useState<Record<string, DataroomDocument[]>>(
    {}
  );
  const [uploading, setUploading] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [investorName, setInvestorName] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  // Redirect unauthenticated users to signup
  useEffect(() => {
    if (sessionStatus === "unauthenticated") {
      router.push(`/auth/signup?callbackUrl=/dataroom/${shareToken}`);
    }
  }, [sessionStatus, router, shareToken]);

  // Fetch dataroom data
  const fetchDataroom = useCallback(async () => {
    if (!token || !shareToken) return;
    try {
      const data = await api.getDataroomByToken(token, shareToken);
      setDataroom(data);

      // Group existing documents by section
      const grouped: Record<string, DataroomDocument[]> = {};
      for (const doc of data.documents || []) {
        if (!grouped[doc.section]) grouped[doc.section] = [];
        grouped[doc.section].push(doc);
      }
      setDocuments(grouped);

      // If already submitted, show thank you state
      if (data.status === "submitted" || data.status === "analyzing" || data.status === "complete") {
        setSubmitted(true);
        setInvestorName(data.investor_name);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load dataroom request");
    }
    setLoading(false);
  }, [token, shareToken]);

  useEffect(() => {
    if (token && shareToken) {
      fetchDataroom();
    }
  }, [token, shareToken, fetchDataroom]);

  // Upload handler
  async function handleUpload(sectionKey: string, files: FileList) {
    if (!token || !shareToken) return;
    setUploading((prev) => ({ ...prev, [sectionKey]: true }));

    for (let i = 0; i < files.length; i++) {
      try {
        const doc = await api.uploadDataroomFile(
          token,
          shareToken,
          sectionKey,
          files[i]
        );
        setDocuments((prev) => ({
          ...prev,
          [sectionKey]: [...(prev[sectionKey] || []), doc],
        }));
      } catch (err: any) {
        setError(err.message || `Failed to upload ${files[i].name}`);
      }
    }

    setUploading((prev) => ({ ...prev, [sectionKey]: false }));
  }

  // Remove handler
  async function handleRemove(sectionKey: string, docId: string) {
    if (!token || !shareToken) return;
    try {
      await api.deleteDataroomDocument(token, shareToken, docId);
      setDocuments((prev) => ({
        ...prev,
        [sectionKey]: (prev[sectionKey] || []).filter((d) => d.id !== docId),
      }));
    } catch (err: any) {
      setError(err.message || "Failed to remove document");
    }
  }

  // Submit handler
  async function handleSubmit() {
    if (!token || !shareToken) return;
    setSubmitting(true);
    setShowConfirm(false);
    try {
      const result = await api.submitDataroom(token, shareToken);
      setSubmitted(true);
      setInvestorName(result.investor_name);
    } catch (err: any) {
      setError(err.message || "Failed to submit dataroom");
    }
    setSubmitting(false);
  }

  const totalFiles = Object.values(documents).reduce(
    (sum, docs) => sum + docs.length,
    0
  );

  // ---- Loading / session loading ----
  if (sessionStatus === "loading" || (sessionStatus === "authenticated" && loading)) {
    return (
      <div className="max-w-2xl mx-auto py-20">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-border rounded w-64" />
          <div className="h-4 bg-border rounded w-48" />
          <div className="h-32 bg-border rounded" />
          <div className="h-32 bg-border rounded" />
        </div>
      </div>
    );
  }

  // ---- Error with no dataroom ----
  if (error && !dataroom) {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center">
        <h1 className="font-serif text-2xl text-text-primary mb-4">
          Unable to Load Dataroom
        </h1>
        <p className="text-text-secondary text-sm">{error}</p>
      </div>
    );
  }

  // ---- Submitted / thank you ----
  if (submitted) {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-score-high/10 mb-6">
          <span className="text-score-high text-3xl">&#10003;</span>
        </div>
        <h1 className="font-serif text-2xl text-text-primary mb-3">
          Thank You
        </h1>
        <p className="text-text-secondary text-sm">
          Your dataroom has been shared with{" "}
          <span className="font-medium text-text-primary">
            {investorName || "the investor"}
          </span>
          .
        </p>
      </div>
    );
  }

  // ---- Normal upload interface ----
  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="font-serif text-2xl text-text-primary mb-1">
        Upload Your Dataroom
      </h1>

      {dataroom?.company_name && (
        <p className="text-text-secondary text-sm mb-4">
          {dataroom.company_name}
        </p>
      )}

      {/* Investor's personal message */}
      {dataroom?.personal_message && (
        <div className="mb-6 rounded bg-bg-secondary border-l-4 border-accent px-4 py-3">
          <p className="text-sm text-text-secondary italic whitespace-pre-line">
            {dataroom.personal_message}
          </p>
          {dataroom.investor_name && (
            <p className="text-xs text-text-tertiary mt-2">
              &mdash; {dataroom.investor_name}
            </p>
          )}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="mb-4 rounded border border-score-low/20 bg-score-low/10 px-4 py-3 text-sm text-score-low">
          {error}
        </div>
      )}

      {/* Sections */}
      <div className="space-y-6">
        {SECTIONS.map((section) => (
          <div key={section.key}>
            <h2 className="text-sm font-medium text-text-primary mb-1">
              {section.title}
            </h2>
            <p className="text-xs text-text-tertiary mb-2">
              {section.description}
            </p>
            <DropZone
              sectionKey={section.key}
              documents={documents[section.key] || []}
              onUpload={(files) => handleUpload(section.key, files)}
              onRemove={(docId) => handleRemove(section.key, docId)}
              uploading={uploading[section.key] || false}
            />
          </div>
        ))}
      </div>

      {/* Submit button */}
      <div className="mt-8 mb-12">
        <button
          onClick={() => setShowConfirm(true)}
          disabled={totalFiles === 0 || submitting}
          className="w-full rounded bg-accent px-4 py-3 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50 transition"
        >
          {submitting
            ? "Submitting..."
            : `Submit Dataroom (${totalFiles} file${totalFiles !== 1 ? "s" : ""})`}
        </button>
      </div>

      {/* Confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-surface rounded-lg shadow-xl max-w-sm w-full mx-4 p-6">
            <h3 className="text-lg font-medium text-text-primary mb-2">
              Submit Dataroom?
            </h3>
            <p className="text-sm text-text-secondary mb-6">
              You are about to share {totalFiles} file
              {totalFiles !== 1 ? "s" : ""} with{" "}
              <span className="font-medium">
                {dataroom?.investor_name || "the investor"}
              </span>
              . This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowConfirm(false)}
                className="px-4 py-2 text-sm rounded border border-border text-text-primary hover:bg-bg-secondary transition"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                className="px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition font-medium"
              >
                Submit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
