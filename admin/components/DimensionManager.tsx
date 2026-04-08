"use client";

import { useState } from "react";
import type { DDTemplate, Dimension } from "@/lib/types";

interface DimensionManagerProps {
  dimensions: Dimension[];
  templates: DDTemplate[];
  onApplyTemplate: (templateId: string) => Promise<void>;
  onSaveDimensions: (dims: { dimension_name: string; weight: number; sort_order: number }[]) => Promise<void>;
}

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
        <h3 className="text-lg font-medium">Dimensions</h3>
        <select
          onChange={async (e) => {
            if (e.target.value) {
              await onApplyTemplate(e.target.value);
              e.target.value = "";
            }
          }}
          className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
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
              className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
            />
            <input
              type="number"
              step="0.1"
              value={dim.weight}
              onChange={(e) => updateDim(i, "weight", parseFloat(e.target.value) || 1.0)}
              className="w-20 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
            />
            <button
              onClick={() => removeDimension(i)}
              className="text-red-400 hover:text-red-300 text-sm"
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={addDimension}
          className="px-3 py-1 text-sm bg-gray-800 text-gray-300 rounded hover:bg-gray-700"
        >
          + Add Dimension
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save Dimensions"}
        </button>
      </div>
    </div>
  );
}
