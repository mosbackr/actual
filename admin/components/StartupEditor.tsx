"use client";

import { useState } from "react";

interface StartupEditorProps {
  initial: {
    name: string;
    description: string;
    website_url: string | null;
    stage: string;
    status: string;
    location_city: string | null;
    location_state: string | null;
    location_country: string;
  };
  onSave: (data: Record<string, string>) => Promise<void>;
}

const STAGES = ["pre_seed", "seed", "series_a", "series_b", "series_c", "growth"];
const STATUSES = ["pending", "approved", "rejected", "featured"];

const inputClasses =
  "w-full bg-surface border border-border rounded px-3 py-2 text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

export function StartupEditor({ initial, onSave }: StartupEditorProps) {
  const [form, setForm] = useState({
    name: initial.name,
    description: initial.description,
    website_url: initial.website_url || "",
    stage: initial.stage,
    status: initial.status,
    location_city: initial.location_city || "",
    location_state: initial.location_state || "",
    location_country: initial.location_country,
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(form);
    } finally {
      setSaving(false);
    }
  }

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm text-text-secondary mb-1">Name</label>
        <input
          value={form.name}
          onChange={(e) => update("name", e.target.value)}
          className={inputClasses}
        />
      </div>
      <div>
        <label className="block text-sm text-text-secondary mb-1">Description</label>
        <textarea
          value={form.description}
          onChange={(e) => update("description", e.target.value)}
          rows={4}
          className={inputClasses}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-text-secondary mb-1">Stage</label>
          <select
            value={form.stage}
            onChange={(e) => update("stage", e.target.value)}
            className={inputClasses}
          >
            {STAGES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-sm text-text-secondary mb-1">Status</label>
          <select
            value={form.status}
            onChange={(e) => update("status", e.target.value)}
            className={inputClasses}
          >
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-sm text-text-secondary mb-1">Website URL</label>
        <input
          value={form.website_url}
          onChange={(e) => update("website_url", e.target.value)}
          className={inputClasses}
        />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-sm text-text-secondary mb-1">City</label>
          <input
            value={form.location_city}
            onChange={(e) => update("location_city", e.target.value)}
            className={inputClasses}
          />
        </div>
        <div>
          <label className="block text-sm text-text-secondary mb-1">State</label>
          <input
            value={form.location_state}
            onChange={(e) => update("location_state", e.target.value)}
            className={inputClasses}
          />
        </div>
        <div>
          <label className="block text-sm text-text-secondary mb-1">Country</label>
          <input
            value={form.location_country}
            onChange={(e) => update("location_country", e.target.value)}
            className={inputClasses}
          />
        </div>
      </div>
      <button
        type="submit"
        disabled={saving}
        className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 transition"
      >
        {saving ? "Saving..." : "Save Changes"}
      </button>
    </form>
  );
}
