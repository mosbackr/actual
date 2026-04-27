"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
  public: "Public",
};

interface Suggestion {
  company_name: string;
  matched_startup: {
    id: string;
    slug: string;
    name: string;
    logo_url: string | null;
    stage: string | null;
  } | null;
}

export function ClaimBanner({
  investorId,
  token,
  onClaimed,
}: {
  investorId: string;
  token: string;
  onClaimed: () => void;
}) {
  const [claiming, setClaiming] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  async function handleClaim() {
    setClaiming(true);
    try {
      const result = await api.claimInvestorProfile(token);
      if (result.already_claimed) {
        onClaimed();
        return;
      }
      // Load suggestions
      const { suggestions: sugs } = await api.getSuggestedPortfolio(token, result.investor_id);
      if (sugs.length === 0) {
        onClaimed();
        return;
      }
      setSuggestions(sugs);
      setChecked(new Set(sugs.map((s) => s.company_name)));
    } catch {
      // If claim fails (404 = no match), just hide the banner
    }
    setClaiming(false);
  }

  async function handleConfirm() {
    setSaving(true);
    for (const sug of suggestions || []) {
      if (!checked.has(sug.company_name)) continue;
      try {
        await api.addPortfolioCompany(token, investorId, {
          company_name: sug.matched_startup?.name || sug.company_name,
          startup_id: sug.matched_startup?.id,
        });
      } catch {
        // Skip duplicates or errors
      }
    }
    setSaving(false);
    onClaimed();
  }

  function toggleCheck(name: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  // Suggestion confirmation view
  if (suggestions) {
    return (
      <div className="rounded border border-accent/30 bg-accent/5 p-6 mb-10">
        <h3 className="font-serif text-lg text-text-primary mb-2">
          We found these investments — are these yours?
        </h3>
        <p className="text-sm text-text-secondary mb-4">
          Uncheck any that don&apos;t belong to you.
        </p>
        <div className="space-y-2 mb-4">
          {suggestions.map((sug) => (
            <label
              key={sug.company_name}
              className="flex items-center gap-3 rounded border border-border bg-surface p-3 cursor-pointer hover:border-text-tertiary transition"
            >
              <input
                type="checkbox"
                checked={checked.has(sug.company_name)}
                onChange={() => toggleCheck(sug.company_name)}
                className="accent-accent"
              />
              {sug.matched_startup?.logo_url ? (
                <img
                  src={sug.matched_startup.logo_url}
                  alt={sug.company_name}
                  className="h-8 w-8 rounded object-cover"
                />
              ) : (
                <div className="h-8 w-8 rounded bg-background border border-border flex items-center justify-center font-serif text-sm text-text-tertiary">
                  {sug.company_name[0]}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-text-primary truncate">
                  {sug.matched_startup?.name || sug.company_name}
                </p>
                {sug.matched_startup?.stage && (
                  <p className="text-xs text-text-tertiary">
                    {stageLabels[sug.matched_startup.stage] || sug.matched_startup.stage}
                  </p>
                )}
              </div>
              {sug.matched_startup && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-score-high/10 text-score-high font-medium">
                  Matched
                </span>
              )}
            </label>
          ))}
        </div>
        <button
          onClick={handleConfirm}
          disabled={saving || checked.size === 0}
          className="px-6 py-2.5 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover disabled:opacity-50 transition"
        >
          {saving ? "Saving..." : `Confirm ${checked.size} Companies`}
        </button>
      </div>
    );
  }

  // Initial claim banner
  return (
    <div className="rounded border border-accent/30 bg-accent/5 p-4 mb-10 flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-text-primary">
          Is this you? Claim your profile to manage your portfolio.
        </p>
      </div>
      <button
        onClick={handleClaim}
        disabled={claiming}
        className="px-4 py-2 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover disabled:opacity-50 transition shrink-0"
      >
        {claiming ? "Claiming..." : "Claim Profile"}
      </button>
    </div>
  );
}
