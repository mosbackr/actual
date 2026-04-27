"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const STAGES = [
  { value: "pre_seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c", label: "Series C" },
  { value: "growth", label: "Growth" },
];

interface StartupResult {
  id: string;
  slug: string;
  name: string;
  logo_url: string | null;
  stage: string;
  ai_score: number | null;
}

export function AddCompanyModal({
  open,
  onClose,
  token,
  investorId,
  onAdded,
  prefill,
}: {
  open: boolean;
  onClose: () => void;
  token: string;
  investorId: string;
  onAdded: () => void;
  prefill?: { startup_id: string; company_name: string };
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StartupResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedStartup, setSelectedStartup] = useState<StartupResult | null>(null);
  const [manualMode, setManualMode] = useState(false);

  // Form fields
  const [companyName, setCompanyName] = useState("");
  const [companyWebsite, setCompanyWebsite] = useState("");
  const [roundStage, setRoundStage] = useState("");
  const [investmentDate, setInvestmentDate] = useState("");
  const [checkSize, setCheckSize] = useState("");
  const [isLead, setIsLead] = useState(false);
  const [boardSeat, setBoardSeat] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Prefill support (for startup page button)
  useEffect(() => {
    if (open && prefill) {
      setCompanyName(prefill.company_name);
      setSelectedStartup({ id: prefill.startup_id, name: prefill.company_name } as StartupResult);
      setManualMode(false);
    }
  }, [open, prefill]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setSelectedStartup(null);
      setManualMode(false);
      setCompanyName("");
      setCompanyWebsite("");
      setRoundStage("");
      setInvestmentDate("");
      setCheckSize("");
      setIsLead(false);
      setBoardSeat(false);
      setError("");
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const params = new URLSearchParams({ q: query, per_page: "5" });
        const res = await fetch(`${API_URL}/api/startups?${params}`);
        if (res.ok) {
          const data = await res.json();
          setResults(data.items || []);
        }
      } catch { /* ignore */ }
      setSearching(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const handleKey = useCallback(
    (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); },
    [onClose]
  );

  useEffect(() => {
    if (open) document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, handleKey]);

  function selectStartup(s: StartupResult) {
    setSelectedStartup(s);
    setCompanyName(s.name);
    setQuery("");
    setResults([]);
  }

  async function handleSubmit() {
    if (!companyName.trim()) {
      setError("Company name is required");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.addPortfolioCompany(token, investorId, {
        company_name: companyName.trim(),
        startup_id: selectedStartup?.id,
        company_website: companyWebsite || undefined,
        investment_date: investmentDate || undefined,
        round_stage: roundStage || undefined,
        check_size: checkSize || undefined,
        is_lead: isLead,
        board_seat: boardSeat,
      });
      onAdded();
      onClose();
    } catch (e: any) {
      setError(e.message || "Failed to add company");
    }
    setSaving(false);
  }

  if (!open) return null;

  const stageLabel = STAGES.find((s) => s.value === (selectedStartup?.stage))?.label;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-text-primary/30 backdrop-blur-sm"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-surface border border-border rounded p-6 w-full max-w-md mx-4 shadow-lg max-h-[90vh] overflow-y-auto">
        <h3 className="font-serif text-lg text-text-primary mb-4">Add Company to Portfolio</h3>

        {/* Search / Selected / Manual */}
        {!selectedStartup && !manualMode && !prefill && (
          <div className="mb-4">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search companies..."
              className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            />
            {searching && <p className="text-xs text-text-tertiary mt-1">Searching...</p>}
            {results.length > 0 && (
              <div className="mt-1 border border-border rounded bg-surface divide-y divide-border">
                {results.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => selectStartup(s)}
                    className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-hover-row transition"
                  >
                    {s.logo_url ? (
                      <img src={s.logo_url} alt={s.name} className="h-7 w-7 rounded object-cover" />
                    ) : (
                      <div className="h-7 w-7 rounded bg-background border border-border flex items-center justify-center font-serif text-xs text-text-tertiary">
                        {s.name[0]}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-text-primary truncate">{s.name}</p>
                    </div>
                    {s.ai_score != null && (
                      <span className="text-xs tabular-nums text-text-tertiary">AI: {s.ai_score.toFixed(0)}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
            <button
              onClick={() => setManualMode(true)}
              className="text-xs text-accent hover:text-accent-hover mt-2 transition"
            >
              Company not listed? Add manually
            </button>
          </div>
        )}

        {/* Selected startup chip */}
        {selectedStartup && (
          <div className="flex items-center gap-2 mb-4 rounded border border-score-high/30 bg-score-high/5 px-3 py-2">
            <span className="text-sm text-text-primary flex-1 truncate">{selectedStartup.name}</span>
            {stageLabel && <span className="text-xs text-text-tertiary">{stageLabel}</span>}
            {!prefill && (
              <button
                onClick={() => { setSelectedStartup(null); setCompanyName(""); }}
                className="text-xs text-text-tertiary hover:text-text-primary"
              >
                &times;
              </button>
            )}
          </div>
        )}

        {/* Manual entry fields */}
        {manualMode && !selectedStartup && (
          <div className="space-y-3 mb-4">
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Company name *"
              className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            />
            <input
              type="url"
              value={companyWebsite}
              onChange={(e) => setCompanyWebsite(e.target.value)}
              placeholder="Website (optional)"
              className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            />
          </div>
        )}

        {/* Investment detail form */}
        {(selectedStartup || manualMode) && (
          <div className="space-y-3 mb-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">Round</label>
                <select
                  value={roundStage}
                  onChange={(e) => setRoundStage(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary focus:outline-none focus:border-accent"
                >
                  <option value="">Select...</option>
                  {STAGES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">Date</label>
                <input
                  type="date"
                  value={investmentDate}
                  onChange={(e) => setInvestmentDate(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary focus:outline-none focus:border-accent"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">Check Size</label>
              <input
                type="text"
                value={checkSize}
                onChange={(e) => setCheckSize(e.target.value)}
                placeholder="e.g. $150K"
                className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
              />
            </div>
            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={isLead}
                  onChange={(e) => setIsLead(e.target.checked)}
                  className="accent-accent"
                />
                Lead investor
              </label>
              <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={boardSeat}
                  onChange={(e) => setBoardSeat(e.target.checked)}
                  className="accent-accent"
                />
                Board seat
              </label>
            </div>
          </div>
        )}

        {error && <p className="text-xs text-score-low mb-3">{error}</p>}

        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || (!companyName.trim())}
            className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
          >
            {saving ? "Adding..." : "Add to Portfolio"}
          </button>
        </div>
      </div>
    </div>
  );
}
