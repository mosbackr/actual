"use client";

import { useState } from "react";
import type { DDTemplate, Dimension } from "@/lib/types";

interface DimensionManagerProps {
  dimensions: Dimension[];
  templates: DDTemplate[];
  onApplyTemplate: (templateId: string) => Promise<void>;
  onSaveDimensions: (dims: { dimension_name: string; weight: number; sort_order: number }[]) => Promise<void>;
}

const inputClasses =
  "bg-surface border border-border rounded px-2 py-1 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

export function DimensionManager({
  dimensions,
  templates,
  onApplyTemplate,
  onSaveDimensions,
}: DimensionManagerProps) {
  const [dims, setDims] = useState(
    dimensions.map((d) => ({
      dimension_name: d.dimension_name,
      weight: d.weight,
      sort_order: d.sort_order,
    }))
  );
  const [saving, setSaving] = useState(false);

  function addDimension() {
    setDims([...dims, { dimension_name: "", weight: 1.0, sort_order: dims.length }]);
  }

  function removeDimension(index: number) {
    setDims(dims.filter((_, i) => i !== index));
  }

  function updateDim(index: number, field: string, value: string | number) {
    setDims(dims.map((d, i) => (i === index ? { ...d, [field]: value } : d)));
  }

  async function handleSave() {
    setSaving(true);
    try {
      await onSaveDimensions(dims);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-lg font-medium text-text-primary">Dimensions</h3>
        <select
          onChange={async (e) => {
            if (e.target.value) {
              await onApplyTemplate(e.target.value);
              e.target.value = "";
            }
          }}
          className={inputClasses}
        >
          <option value="">Apply template...</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        {dims.map((dim, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={dim.dimension_name}
              onChange={(e) => updateDim(i, "dimension_name", e.target.value)}
              placeholder="Dimension name"
              className={`flex-1 ${inputClasses}`}
            />
            <input
              type="number"
              step="0.1"
              value={dim.weight}
              onChange={(e) => updateDim(i, "weight", parseFloat(e.target.value) || 1.0)}
              className={`w-20 ${inputClasses}`}
            />
            <button
              onClick={() => removeDimension(i)}
              className="text-score-low hover:opacity-80 text-sm transition"
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={addDimension}
          className="px-3 py-1 text-sm border border-border text-text-secondary rounded hover:text-text-primary hover:border-text-tertiary transition"
        >
          + Add Dimension
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1 text-sm bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 transition"
        >
          {saving ? "Saving..." : "Save Dimensions"}
        </button>
      </div>
    </div>
  );
}
