"use client";

import { useRef, useState } from "react";

interface Props {
  onSend: (message: string) => void;
  onGenerateReport: (format: "docx" | "xlsx" | "pdf" | "pptx") => void;
  isStreaming: boolean;
  hasMessages: boolean;
  isSubscriber: boolean;
}

export function AnalystInput({ onSend, onGenerateReport, isStreaming, hasMessages, isSubscriber }: Props) {
  const [input, setInput] = useState("");
  const [showReportMenu, setShowReportMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
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
    // Auto-resize
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  };

  return (
    <div className="border-t border-border bg-surface px-4 py-3">
      <div className="flex items-end gap-2">
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
          disabled={!input.trim() || isStreaming}
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
                <button
                  onClick={() => { onGenerateReport("pdf"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  PDF (.pdf)
                </button>
                <button
                  onClick={() => { onGenerateReport("docx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  Word (.docx)
                </button>
                <button
                  onClick={() => { onGenerateReport("pptx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  PowerPoint (.pptx)
                </button>
                <button
                  onClick={() => { onGenerateReport("xlsx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  Excel (.xlsx)
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
