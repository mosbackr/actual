"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (prompt: string) => void;
}

interface PromptCategory {
  name: string;
  prompts: string[];
}

const VC_ANALYST: PromptCategory[] = [
  {
    name: "Portfolio Overview",
    prompts: [
      "What's the overall health of our portfolio?",
      "Portfolio sector breakdown and concentration analysis",
      "Which startups have the highest growth potential?",
      "Compare our top 10 startups by AI score",
      "Portfolio vintage analysis — when did our best deals come in?",
    ],
  },
  {
    name: "Deal Flow & Sourcing",
    prompts: [
      "What sectors are underrepresented in our deal flow?",
      "Show me pre-seed startups that could be breakout companies",
      "Which startups recently improved their scores significantly?",
      "Find startups with strong teams but early-stage metrics",
      "Identify companies in emerging categories we should watch",
    ],
  },
  {
    name: "Due Diligence",
    prompts: [
      "Deep dive analysis on our highest-scored startup",
      "Which startups have the most complete profiles?",
      "Compare founding team backgrounds across top startups",
      "Identify red flags or concerns across the portfolio",
      "Due diligence checklist for our newest additions",
    ],
  },
  {
    name: "Market & Sector Analysis",
    prompts: [
      "Fintech funding trends and opportunity map",
      "AI/ML sector landscape and our positioning",
      "Healthcare startup ecosystem analysis",
      "Climate tech investment thesis validation",
      "B2B SaaS market dynamics and our coverage",
    ],
  },
  {
    name: "Competitive Intelligence",
    prompts: [
      "Competitive landscape for our top-scored startups",
      "Which of our startups have the strongest moats?",
      "Market sizing analysis for our portfolio companies",
      "Identify potential acquirers for our mature startups",
      "Benchmark our portfolio against industry averages",
    ],
  },
  {
    name: "Fund Strategy",
    prompts: [
      "Stage distribution analysis — are we balanced?",
      "Geographic diversification of our portfolio",
      "Which startups are ready for follow-on investment?",
      "Portfolio construction optimization suggestions",
      "Pipeline analysis — what's coming through the funnel?",
    ],
  },
];

const QUANTITATIVE: PromptCategory[] = [
  {
    name: "Statistical Analysis",
    prompts: [
      "Score distribution analysis with statistical breakdown",
      "Correlation analysis between funding stage and AI scores",
      "Standard deviation and outlier detection across dimensions",
      "Percentile ranking of all startups by composite score",
      "Statistical summary of key metrics across the portfolio",
    ],
  },
  {
    name: "Scoring & Ranking",
    prompts: [
      "Rank all startups by weighted dimension scores",
      "Which dimension contributes most to top performers?",
      "Score gap analysis — where are the biggest improvements needed?",
      "Create a tiered ranking system (A/B/C) for the portfolio",
      "Multi-factor scoring comparison across sectors",
    ],
  },
  {
    name: "Trend Analysis",
    prompts: [
      "Month-over-month score trends for the portfolio",
      "Emerging trend detection in startup descriptions",
      "Funding velocity trends by sector",
      "Score trajectory predictions for top startups",
      "Seasonal patterns in deal flow and scoring",
    ],
  },
  {
    name: "Financial Modeling",
    prompts: [
      "Funding efficiency analysis — dollars raised vs. score",
      "Valuation distribution across the portfolio",
      "Burn rate estimation based on funding and stage",
      "Expected return modeling by stage and sector",
      "Capital allocation optimization across portfolio",
    ],
  },
  {
    name: "Risk Assessment",
    prompts: [
      "Risk concentration analysis by sector and stage",
      "Identify startups with declining score trajectories",
      "Portfolio stress test — what if our top sector underperforms?",
      "Survivorship probability analysis by funding stage",
      "Correlation risk — which startups move together?",
    ],
  },
  {
    name: "Visualization & Reporting",
    prompts: [
      "Generate a portfolio heat map by sector and score",
      "Create a bubble chart of startups by funding vs. score",
      "Funding stage pipeline visualization",
      "Dimension radar chart for top 5 startups",
      "Executive summary dashboard of portfolio health",
    ],
  },
];

export function PromptSuggestionsModal({ open, onClose, onSelect }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<"analyst" | "quantitative">("analyst");

  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKey);
      setSearch("");
    }
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, handleKey]);

  if (!open) return null;

  const categories = activeTab === "analyst" ? VC_ANALYST : QUANTITATIVE;
  const query = search.toLowerCase().trim();

  const filtered = query
    ? categories
        .map((cat) => ({
          ...cat,
          prompts: cat.prompts.filter((p) => p.toLowerCase().includes(query)),
        }))
        .filter((cat) => cat.prompts.length > 0)
    : categories;

  const totalResults = filtered.reduce((sum, cat) => sum + cat.prompts.length, 0);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-text-primary/30 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="bg-surface border border-border rounded-lg w-full max-w-2xl mx-4 shadow-lg flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="p-4 border-b border-border">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-text-primary">Suggested Prompts</h3>
            <button
              onClick={onClose}
              className="text-text-tertiary hover:text-text-secondary transition"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Search prompts..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
            className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent"
          />

          {/* Tabs */}
          <div className="flex gap-1 mt-3">
            <button
              onClick={() => setActiveTab("analyst")}
              className={`px-3 py-1.5 text-xs font-medium rounded transition ${
                activeTab === "analyst"
                  ? "bg-accent text-white"
                  : "text-text-tertiary hover:text-text-secondary hover:bg-background"
              }`}
            >
              VC Analyst
            </button>
            <button
              onClick={() => setActiveTab("quantitative")}
              className={`px-3 py-1.5 text-xs font-medium rounded transition ${
                activeTab === "quantitative"
                  ? "bg-accent text-white"
                  : "text-text-tertiary hover:text-text-secondary hover:bg-background"
              }`}
            >
              Quantitative
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {filtered.length === 0 ? (
            <p className="text-sm text-text-tertiary text-center py-8">
              No prompts match &ldquo;{search}&rdquo;
            </p>
          ) : (
            <div className="space-y-4">
              {filtered.map((cat) => (
                <div key={cat.name}>
                  <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1.5">
                    {cat.name}
                  </p>
                  <div className="space-y-0.5">
                    {cat.prompts.map((prompt) => (
                      <button
                        key={prompt}
                        onClick={() => {
                          onSelect(prompt);
                          onClose();
                        }}
                        className="w-full text-left px-3 py-2 rounded text-sm text-text-secondary hover:text-text-primary hover:bg-background transition"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-border">
          <p className="text-[10px] text-text-tertiary">
            {query ? `${totalResults} result${totalResults !== 1 ? "s" : ""}` : "60 prompts"} — click to send
          </p>
        </div>
      </div>
    </div>
  );
}
