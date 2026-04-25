"use client";

import { useState } from "react";
import type { InvestorFAQ, InvestorFAQQuestion } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  market: "Market & Opportunity",
  traction: "Traction & Growth",
  financials: "Financials & Unit Economics",
  team: "Team & Leadership",
  technology: "Technology & Product",
  competition: "Competition & Moat",
  business_model: "Business Model & GTM",
  risk: "Risks & Challenges",
};

const PRIORITY_STYLES: Record<string, string> = {
  high: "bg-score-low/10 text-score-low border-score-low/20",
  medium: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
  low: "bg-text-tertiary/10 text-text-tertiary border-text-tertiary/20",
};

export default function InvestorFaqView({
  faq,
  onRegenerate,
  regenerating,
}: {
  faq: InvestorFAQ;
  onRegenerate: () => void;
  regenerating: boolean;
}) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  // Group questions by category
  const grouped: Record<string, InvestorFAQQuestion[]> = {};
  for (const q of faq.questions) {
    const cat = q.category || "risk";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(q);
  }

  // Order categories by which appear first in the questions array
  const categoryOrder = Object.keys(CATEGORY_LABELS).filter((c) => grouped[c]);

  let globalIndex = 0;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-xs text-text-tertiary">
            Generated {new Date(faq.generated_at).toLocaleDateString()} · {faq.questions.length} questions
          </p>
        </div>
        <button
          onClick={onRegenerate}
          disabled={regenerating}
          className="px-3 py-1.5 text-xs font-medium rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition disabled:opacity-50"
        >
          {regenerating ? "Regenerating..." : "Regenerate"}
        </button>
      </div>

      {/* Questions grouped by category */}
      {categoryOrder.map((category) => {
        const questions = grouped[category];
        return (
          <div key={category} className="mb-6">
            <h3 className="text-sm font-medium text-text-primary mb-3 uppercase tracking-wide">
              {CATEGORY_LABELS[category] || category}
            </h3>
            <div className="space-y-2">
              {questions.map((q) => {
                const idx = globalIndex++;
                const isOpen = openIndex === idx;
                return (
                  <div
                    key={idx}
                    className="rounded-lg border border-border bg-surface overflow-hidden"
                  >
                    <button
                      onClick={() => setOpenIndex(isOpen ? null : idx)}
                      className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-surface-hover transition"
                    >
                      <span
                        className={`mt-0.5 text-[10px] px-1.5 py-0.5 rounded border font-medium shrink-0 ${PRIORITY_STYLES[q.priority] || PRIORITY_STYLES.low}`}
                      >
                        {q.priority}
                      </span>
                      <span className="text-sm text-text-primary flex-1">
                        {q.question}
                      </span>
                      <span className="text-text-tertiary text-xs mt-0.5 shrink-0">
                        {isOpen ? "−" : "+"}
                      </span>
                    </button>
                    {isOpen && (
                      <div className="px-4 pb-4 pt-0 ml-[42px]">
                        <p className="text-sm text-text-secondary leading-relaxed">
                          {q.answer}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
