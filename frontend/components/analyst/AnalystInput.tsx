"use client";

import { useRef, useState, useEffect } from "react";

const ALLOWED_EXTENSIONS = new Set([
  "pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv", "md", "txt",
  "png", "jpg", "jpeg", "gif", "webp",
]);
const MAX_FILE_SIZE = 20 * 1024 * 1024;
const MAX_FILES = 10;

interface Props {
  onSend: (message: string, files?: File[]) => void;
  onGenerateReport: (format: "docx" | "xlsx" | "pdf" | "pptx") => void;
  isStreaming: boolean;
  hasMessages: boolean;
  isSubscriber: boolean;
  externalFiles?: File[];
  onClearExternalFiles?: () => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function AnalystInput({ onSend, onGenerateReport, isStreaming, hasMessages, isSubscriber, externalFiles, onClearExternalFiles }: Props) {
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [showReportMenu, setShowReportMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateAndAddFiles = (newFiles: FileList | File[]) => {
    setFileError(null);
    const filesToAdd: File[] = [];

    for (const file of Array.from(newFiles)) {
      const ext = file.name.split(".").pop()?.toLowerCase() || "";
      if (!ALLOWED_EXTENSIONS.has(ext)) {
        setFileError(`Unsupported file type: .${ext}`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setFileError(`${file.name} exceeds 20MB limit`);
        return;
      }
      filesToAdd.push(file);
    }

    const total = attachedFiles.length + filesToAdd.length;
    if (total > MAX_FILES) {
      setFileError(`Maximum ${MAX_FILES} files allowed`);
      return;
    }

    setAttachedFiles((prev) => [...prev, ...filesToAdd]);
  };

  // Merge externally dropped files
  useEffect(() => {
    if (externalFiles && externalFiles.length > 0) {
      validateAndAddFiles(externalFiles);
      onClearExternalFiles?.();
    }
  }, [externalFiles]);

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
    setFileError(null);
  };

  const handleSubmit = () => {
    const trimmed = input.trim();
    if ((!trimmed && attachedFiles.length === 0) || isStreaming) return;
    onSend(trimmed || "Please analyze the attached files.", attachedFiles.length > 0 ? attachedFiles : undefined);
    setInput("");
    setAttachedFiles([]);
    setFileError(null);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  };

  const fileTypeIcon = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase() || "";
    const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp"]);
    if (IMAGE_EXTS.has(ext)) return "\u{1F5BC}";
    if (ext === "pdf") return "\u{1F4C4}";
    if (["docx", "doc"].includes(ext)) return "\u{1F4DD}";
    if (["pptx", "ppt"].includes(ext)) return "\u{1F4CA}";
    if (["xlsx", "xls", "csv"].includes(ext)) return "\u{1F4CA}";
    return "\u{1F4CE}";
  };

  return (
    <div className="border-t border-border bg-surface px-4 py-3">
      {/* File preview bar */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachedFiles.map((file, i) => (
            <div
              key={`${file.name}-${i}`}
              className="flex items-center gap-1.5 bg-background border border-border rounded px-2 py-1 text-xs"
            >
              <span>{fileTypeIcon(file.name)}</span>
              <span className="text-text-primary truncate max-w-[150px]">{file.name}</span>
              <span className="text-text-tertiary">({formatSize(file.size)})</span>
              <button
                onClick={() => removeFile(i)}
                className="text-text-tertiary hover:text-score-low ml-1"
              >
                x
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Error message */}
      {fileError && (
        <p className="text-xs text-score-low mb-2">{fileError}</p>
      )}

      <div className="flex items-end gap-2">
        {/* Attach button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          className="px-2 py-2 text-text-tertiary hover:text-text-primary disabled:opacity-50 transition"
          title="Attach files"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.csv,.md,.txt,.png,.jpg,.jpeg,.gif,.webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) validateAndAddFiles(e.target.files);
            e.target.value = "";
          }}
        />

        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your portfolio, market trends, competitor analysis..."
          rows={1}
          disabled={isStreaming}
          className="flex-1 resize-none rounded border border-border bg-background px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent disabled:opacity-50"
        />

        <button
          onClick={handleSubmit}
          disabled={(!input.trim() && attachedFiles.length === 0) || isStreaming}
          className="px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {isStreaming ? "..." : "Send"}
        </button>

        {hasMessages && (
          <div className="relative">
            <button
              onClick={() => setShowReportMenu(!showReportMenu)}
              disabled={isStreaming}
              className="px-3 py-2 text-xs rounded border border-border text-text-secondary hover:text-text-primary hover:border-accent/50 disabled:opacity-50 transition whitespace-nowrap"
              title={isSubscriber ? "Generate report" : "Subscribe to generate reports"}
            >
              Report
            </button>
            {showReportMenu && (
              <div className="absolute bottom-full right-0 mb-1 bg-surface border border-border rounded shadow-lg py-1 z-10">
                <button onClick={() => { onGenerateReport("pdf"); setShowReportMenu(false); }} className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt">PDF (.pdf)</button>
                <button onClick={() => { onGenerateReport("docx"); setShowReportMenu(false); }} className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt">Word (.docx)</button>
                <button onClick={() => { onGenerateReport("pptx"); setShowReportMenu(false); }} className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt">PowerPoint (.pptx)</button>
                <button onClick={() => { onGenerateReport("xlsx"); setShowReportMenu(false); }} className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt">Excel (.xlsx)</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
