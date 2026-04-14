"use client";

import { useState } from "react";

interface Props {
  shareUrl: string;
  onClose: () => void;
}

export function ShareModal({ shareUrl, onClose }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-medium text-text-primary mb-3">Share Conversation</h3>
        <p className="text-xs text-text-tertiary mb-4">
          Anyone with this link can view the conversation (read-only).
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            value={shareUrl}
            readOnly
            className="flex-1 px-3 py-2 text-xs bg-background border border-border rounded text-text-primary"
          />
          <button
            onClick={handleCopy}
            className="px-4 py-2 text-xs rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>

        <button
          onClick={onClose}
          className="mt-4 w-full text-center text-xs text-text-tertiary hover:text-text-secondary"
        >
          Close
        </button>
      </div>
    </div>
  );
}
