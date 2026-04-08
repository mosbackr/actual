"use client";

import { useState } from "react";

interface DimForm {
  dimension_name: string;
  weight: number;
  sort_order: number;
}

interface TemplateEditorProps {
  initial?: { name: string; description: string; dimensions: DimForm[] };
  onSave: (data: { name: string; description: string; dimensions: DimForm[] }) => Promise<void>;
  onDelete?: () => Promise<void>;
}

export function TemplateEditor({ initial, onSave, onDelete }: TemplateEditorProps) {
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
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
      await onSave({ name, description, dimensions: dims });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-2xl">
      <div>
        <label className="block text-sm text-gray-400 mb-1">Template Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-2">Dimensions</label>
        <div className="space-y-2">
          {dims.map((dim, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                value={dim.dimension_name}
                onChange={(e) => updateDim(i, "dimension_name", e.target.value)}
                placeholder="Dimension name"
                required
                className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
              />
              <label className="text-xs text-gray-500">Weight:</label>
              <input
                type="number"
                step="0.1"
                value={dim.weight}
                onChange={(e) => updateDim(i, "weight", parseFloat(e.target.value) || 1.0)}
                className="w-20 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
              />
              <button type="button" onClick={() => removeDim(i)} className="text-red-400 hover:text-red-300 text-sm">
                Remove
              </button>
            </div>
          ))}
        </div>
        <button type="button" onClick={addDim} className="mt-2 text-sm text-indigo-400 hover:text-indigo-300">
          + Add Dimension
        </button>
      </div>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : initial ? "Update Template" : "Create Template"}
        </button>
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600"
          >
            Delete
          </button>
        )}
      </div>
    </form>
  );
}
