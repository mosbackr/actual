"use client";

import { useState } from "react";

interface DimForm {
  dimension_name: string;
  weight: number;
  sort_order: number;
}

interface TemplateData {
  name: string;
  description: string;
  industry_slug: string;
  stage: string;
  dimensions: DimForm[];
}

interface TemplateEditorProps {
  initial?: TemplateData;
  onSave: (data: TemplateData) => Promise<void>;
  onDelete?: () => Promise<void>;
}

const STAGES = [
  { value: "", label: "All Stages" },
  { value: "pre_seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c", label: "Series C" },
  { value: "growth", label: "Growth" },
];

const INDUSTRIES = [
  { value: "", label: "All Industries" },
  { value: "fintech", label: "Fintech" },
  { value: "healthcare", label: "Healthcare" },
  { value: "edtech", label: "EdTech" },
  { value: "cleantech", label: "CleanTech" },
  { value: "saas", label: "SaaS" },
  { value: "e-commerce", label: "E-Commerce" },
  { value: "logistics", label: "Logistics" },
  { value: "ai-ml", label: "AI/ML" },
  { value: "cybersecurity", label: "Cybersecurity" },
  { value: "biotech", label: "BioTech" },
  { value: "proptech", label: "PropTech" },
  { value: "insurtech", label: "InsurTech" },
  { value: "foodtech", label: "FoodTech" },
  { value: "agtech", label: "AgTech" },
  { value: "spacetech", label: "SpaceTech" },
  { value: "robotics", label: "Robotics" },
  { value: "gaming", label: "Gaming" },
  { value: "media", label: "Media" },
  { value: "enterprise-software", label: "Enterprise Software" },
  { value: "consumer-apps", label: "Consumer Apps" },
];

const inputClasses =
  "w-full bg-surface border border-border rounded px-3 py-2 text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

const smallInputClasses =
  "bg-surface border border-border rounded px-2 py-1 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

const selectClasses =
  "bg-surface border border-border rounded px-3 py-2 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

export function TemplateEditor({ initial, onSave, onDelete }: TemplateEditorProps) {
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [industrySlug, setIndustrySlug] = useState(initial?.industry_slug || "");
  const [stage, setStage] = useState(initial?.stage || "");
  const [dims, setDims] = useState<DimForm[]>(
    initial?.dimensions || [{ dimension_name: "", weight: 1.0, sort_order: 0 }]
  );
  const [saving, setSaving] = useState(false);

  function addDim() {
    setDims([...dims, { dimension_name: "", weight: 1.0, sort_order: dims.length }]);
  }

  function removeDim(i: number) {
    setDims(dims.filter((_, idx) => idx !== i));
  }

  function updateDim(i: number, field: string, value: string | number) {
    setDims(dims.map((d, idx) => (idx === i ? { ...d, [field]: value } : d)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({
        name,
        description,
        industry_slug: industrySlug || "",
        stage: stage || "",
        dimensions: dims,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-2xl">
      <div>
        <label className="block text-sm text-text-secondary mb-1">Template Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className={inputClasses}
        />
      </div>
      <div>
        <label className="block text-sm text-text-secondary mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className={inputClasses}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-text-secondary mb-1">Industry</label>
          <select
            value={industrySlug}
            onChange={(e) => setIndustrySlug(e.target.value)}
            className={`w-full ${selectClasses}`}
          >
            {INDUSTRIES.map((ind) => (
              <option key={ind.value} value={ind.value}>{ind.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-text-secondary mb-1">Stage</label>
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value)}
            className={`w-full ${selectClasses}`}
          >
            {STAGES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-sm text-text-secondary mb-2">Dimensions</label>
        <div className="space-y-2">
          {dims.map((dim, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                value={dim.dimension_name}
                onChange={(e) => updateDim(i, "dimension_name", e.target.value)}
                placeholder="Dimension name"
                required
                className={`flex-1 ${smallInputClasses}`}
              />
              <label className="text-xs text-text-tertiary">Weight:</label>
              <input
                type="number"
                step="0.1"
                value={dim.weight}
                onChange={(e) => updateDim(i, "weight", parseFloat(e.target.value) || 1.0)}
                className={`w-20 ${smallInputClasses}`}
              />
              <button type="button" onClick={() => removeDim(i)} className="text-score-low hover:opacity-80 text-sm transition">
                Remove
              </button>
            </div>
          ))}
        </div>
        <button type="button" onClick={addDim} className="mt-2 text-sm text-accent hover:text-accent-hover transition">
          + Add Dimension
        </button>
      </div>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 transition"
        >
          {saving ? "Saving..." : initial ? "Update Template" : "Create Template"}
        </button>
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="px-4 py-2 bg-score-low text-white rounded hover:opacity-90 transition"
          >
            Delete
          </button>
        )}
      </div>
    </form>
  );
}
