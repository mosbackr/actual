"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AddCompanyModal } from "./add-company-modal";
import { ConfirmModal } from "@/components/Modal";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
  public: "Public",
};

const statusStyles: Record<string, string> = {
  active: "border-score-high/30 text-score-high",
  exited: "border-accent/30 text-accent",
  written_off: "border-score-low/30 text-score-low",
};

interface PortfolioItem {
  id: string;
  investor_id: string;
  startup_id: string | null;
  company_name: string;
  company_website: string | null;
  investment_date: string | null;
  round_stage: string | null;
  check_size: string | null;
  is_lead: boolean;
  board_seat: boolean;
  status: string;
  exit_type: string | null;
  exit_multiple: number | null;
  is_public: boolean;
  startup_slug: string | null;
  startup_logo_url: string | null;
  startup_stage: string | null;
}

export function PortfolioSection({
  investorId,
  token,
}: {
  investorId: string;
  token: string | null;
}) {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [isOwner, setIsOwner] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PortfolioItem | null>(null);

  // Suggested portfolio bootstrap state
  interface Suggestion {
    company_name: string;
    matched_startup: {
      id: string; slug: string; name: string; logo_url: string | null; stage: string | null;
    } | null;
  }
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);

  async function loadPortfolio() {
    try {
      const data = await api.getPortfolio(token, investorId);
      setItems(data.items);
      setIsOwner(data.is_owner);

      // If owner with empty portfolio, auto-fetch suggestions
      if (data.is_owner && data.items.length === 0 && token) {
        try {
          const { suggestions: sugs } = await api.getSuggestedPortfolio(token, investorId);
          if (sugs.length > 0) {
            setSuggestions(sugs);
            setChecked(new Set(sugs.map((s) => s.company_name)));
          }
        } catch { /* ignore */ }
      }
    } catch { /* ignore */ }
    setLoading(false);
  }

  useEffect(() => {
    loadPortfolio();
  }, [investorId, token]);

  async function handleImportSuggestions() {
    if (!token || !suggestions) return;
    setImporting(true);
    for (const sug of suggestions) {
      if (!checked.has(sug.company_name)) continue;
      try {
        await api.addPortfolioCompany(token, investorId, {
          company_name: sug.matched_startup?.name || sug.company_name,
          startup_id: sug.matched_startup?.id,
        });
      } catch { /* skip duplicates */ }
    }
    setSuggestions(null);
    setImporting(false);
    loadPortfolio();
  }

  function toggleCheck(name: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function handleDelete() {
    if (!deleteTarget || !token) return;
    try {
      await api.deletePortfolioCompany(token, investorId, deleteTarget.id);
      setItems((prev) => prev.filter((i) => i.id !== deleteTarget.id));
    } catch { /* ignore */ }
    setDeleteTarget(null);
  }

  async function togglePublic(item: PortfolioItem) {
    if (!token) return;
    try {
      await api.updatePortfolioCompany(token, investorId, item.id, {
        is_public: !item.is_public,
      });
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, is_public: !i.is_public } : i))
      );
    } catch { /* ignore */ }
    setMenuOpen(null);
  }

  if (loading) return null;
  if (!isOwner && items.length === 0) return null;

  // Summary stats
  const exitCount = items.filter((i) => i.status === "exited").length;
  const stageCounts: Record<string, number> = {};
  for (const item of items) {
    const s = item.round_stage || "unknown";
    stageCounts[s] = (stageCounts[s] || 0) + 1;
  }
  const topStage = Object.entries(stageCounts).sort((a, b) => b[1] - a[1])[0];

  return (
    <section id="portfolio" className="mb-10 scroll-mt-20">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-serif text-xl text-text-primary">Portfolio</h2>
        {isOwner && (
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            + Add Company
          </button>
        )}
      </div>

      {/* Summary bar (owner only) */}
      {isOwner && items.length > 0 && (
        <p className="text-sm text-text-secondary mb-4">
          {items.length} {items.length === 1 ? "company" : "companies"}
          {exitCount > 0 && ` · ${exitCount} ${exitCount === 1 ? "exit" : "exits"}`}
          {topStage && topStage[0] !== "unknown" && ` · ${stageLabels[topStage[0]] || topStage[0]} focus`}
        </p>
      )}

      {items.length === 0 && isOwner && suggestions && suggestions.length > 0 && (
        <div className="rounded border border-accent/30 bg-accent/5 p-6">
          <h3 className="font-serif text-lg text-text-primary mb-2">
            We found these investments — add them to your portfolio?
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
                  <img src={sug.matched_startup.logo_url} alt={sug.company_name} className="h-8 w-8 rounded object-cover" />
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
          <div className="flex items-center gap-3">
            <button
              onClick={handleImportSuggestions}
              disabled={importing || checked.size === 0}
              className="px-6 py-2.5 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover disabled:opacity-50 transition"
            >
              {importing ? "Importing..." : `Add ${checked.size} Companies`}
            </button>
            <button
              onClick={() => setSuggestions(null)}
              className="text-sm text-text-tertiary hover:text-text-primary transition"
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {items.length === 0 && isOwner && (!suggestions || suggestions.length === 0) && (
        <div className="rounded border border-border bg-surface p-8 text-center">
          <p className="text-sm text-text-tertiary mb-3">No portfolio companies yet.</p>
          <button
            onClick={() => setShowModal(true)}
            className="text-sm text-accent hover:text-accent-hover transition"
          >
            Add your first company
          </button>
        </div>
      )}

      {/* Portfolio grid */}
      {items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item) => (
            <div
              key={item.id}
              className={`relative rounded border border-border bg-surface p-4 hover:border-text-tertiary transition ${
                isOwner && !item.is_public ? "opacity-60" : ""
              }`}
            >
              {/* Menu button (owner only) */}
              {isOwner && (
                <div className="absolute top-3 right-3">
                  <button
                    onClick={() => setMenuOpen(menuOpen === item.id ? null : item.id)}
                    className="text-text-tertiary hover:text-text-primary text-sm px-1"
                  >
                    &middot;&middot;&middot;
                  </button>
                  {menuOpen === item.id && (
                    <div className="absolute right-0 top-6 bg-surface border border-border rounded shadow-lg z-10 py-1 w-40">
                      <button
                        onClick={() => togglePublic(item)}
                        className="w-full text-left px-3 py-1.5 text-xs text-text-secondary hover:bg-hover-row transition"
                      >
                        {item.is_public ? "Make Private" : "Make Public"}
                      </button>
                      <button
                        onClick={() => { setDeleteTarget(item); setMenuOpen(null); }}
                        className="w-full text-left px-3 py-1.5 text-xs text-score-low hover:bg-hover-row transition"
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center gap-3 mb-3">
                {item.startup_logo_url ? (
                  <img src={item.startup_logo_url} alt={item.company_name} className="h-9 w-9 rounded object-cover" />
                ) : (
                  <div className="h-9 w-9 rounded bg-background border border-border flex items-center justify-center font-serif text-sm text-text-tertiary">
                    {item.company_name[0]}
                  </div>
                )}
                <div className="min-w-0 flex-1 pr-6">
                  {item.startup_slug ? (
                    <Link
                      href={`/startups/${item.startup_slug}`}
                      className="text-sm font-medium text-text-primary truncate block hover:text-accent transition"
                    >
                      {item.company_name}
                    </Link>
                  ) : (
                    <p className="text-sm font-medium text-text-primary truncate">{item.company_name}</p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                {item.round_stage && (
                  <span className="text-xs px-2 py-0.5 rounded border border-border text-text-tertiary">
                    {stageLabels[item.round_stage] || item.round_stage}
                  </span>
                )}
                <span className={`text-xs px-2 py-0.5 rounded border ${statusStyles[item.status] || "border-border text-text-tertiary"}`}>
                  {item.status === "written_off" ? "Written Off" : item.status.charAt(0).toUpperCase() + item.status.slice(1)}
                </span>
                {item.is_lead && (
                  <span className="text-xs px-2 py-0.5 rounded border border-accent/30 text-accent">
                    Lead
                  </span>
                )}
                {isOwner && !item.is_public && (
                  <span className="text-xs text-text-tertiary">Private</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {isOwner && (
        <AddCompanyModal
          open={showModal}
          onClose={() => setShowModal(false)}
          token={token!}
          investorId={investorId}
          onAdded={loadPortfolio}
        />
      )}

      <ConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Remove Company"
        message={`Remove ${deleteTarget?.company_name} from your portfolio?`}
        confirmLabel="Remove"
      />
    </section>
  );
}
