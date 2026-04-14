"use client";

import type { AnalystConversationSummary } from "@/lib/types";

const SUGGESTED_ANALYSES = [
  "Portfolio sector breakdown",
  "Score distribution analysis",
  "Funding stage pipeline",
  "Top performers deep dive",
  "Market trend comparison",
  "Competitive landscape overview",
  "Due diligence checklist template",
];

interface Props {
  conversations: AnalystConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSuggestion: (prompt: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

export function AnalystSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onSuggestion,
  isOpen,
  onToggle,
}: Props) {
  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={onToggle}
        className="md:hidden fixed top-20 left-3 z-30 p-2 rounded bg-surface border border-border text-text-secondary hover:text-text-primary"
        aria-label="Toggle sidebar"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Overlay for mobile */}
      {isOpen && (
        <div className="md:hidden fixed inset-0 bg-black/30 z-30" onClick={onToggle} />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:relative z-40 md:z-auto top-0 left-0 h-full w-64 bg-surface border-r border-border flex flex-col transition-transform md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* New button */}
        <div className="p-3 border-b border-border">
          <button
            onClick={onNew}
            className="w-full px-3 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            + New Conversation
          </button>
        </div>

        {/* History */}
        <div className="flex-1 overflow-y-auto">
          {conversations.length > 0 && (
            <div className="p-3">
              <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-2">History</p>
              <div className="space-y-0.5">
                {conversations.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => onSelect(c.id)}
                    className={`w-full text-left px-2 py-1.5 rounded text-sm truncate transition ${
                      activeId === c.id
                        ? "bg-accent/10 text-accent"
                        : "text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                    }`}
                    title={c.title}
                  >
                    {c.title}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Suggestions */}
          <div className="p-3 border-t border-border">
            <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-2">Suggested</p>
            <div className="space-y-0.5">
              {SUGGESTED_ANALYSES.map((s) => (
                <button
                  key={s}
                  onClick={() => onSuggestion(s)}
                  className="w-full text-left px-2 py-1.5 rounded text-xs text-text-tertiary hover:text-text-secondary hover:bg-surface-alt transition truncate"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
