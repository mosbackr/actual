"use client";

import { useState } from "react";
import type { ApprovedExpert, Assignment } from "@/lib/types";

interface ExpertPickerProps {
  experts: ApprovedExpert[];
  assignments: Assignment[];
  onAssign: (expertId: string) => Promise<void>;
  onRemoveAssignment: (assignmentId: string) => Promise<void>;
}

export function ExpertPicker({
  experts,
  assignments,
  onAssign,
  onRemoveAssignment,
}: ExpertPickerProps) {
  const [search, setSearch] = useState("");
  const [assigning, setAssigning] = useState<string | null>(null);

  const assignedExpertIds = new Set(assignments.map((a) => a.expert_id));

  const filtered = experts.filter(
    (e) =>
      !assignedExpertIds.has(e.id) &&
      (e.bio.toLowerCase().includes(search.toLowerCase()) ||
        e.industries.some((i) => i.name.toLowerCase().includes(search.toLowerCase())) ||
        e.skills.some((s) => s.name.toLowerCase().includes(search.toLowerCase())))
  );

  async function handleAssign(expertId: string) {
    setAssigning(expertId);
    try {
      await onAssign(expertId);
    } finally {
      setAssigning(null);
    }
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium text-text-primary">Expert Assignments</h3>

      {assignments.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-text-secondary">Assigned:</p>
          {assignments.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-surface border border-border rounded px-3 py-2">
              <span className="text-sm text-text-primary">
                Expert {a.expert_id.slice(0, 8)}... —{" "}
                <span className={a.status === "accepted" ? "text-score-high" : a.status === "declined" ? "text-score-low" : "text-score-mid"}>
                  {a.status}
                </span>
              </span>
              <button
                onClick={() => onRemoveAssignment(a.id)}
                className="text-xs text-score-low hover:opacity-80 transition"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search experts by industry, skill, or bio..."
          className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none"
        />
      </div>

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {filtered.map((e) => (
          <div key={e.id} className="flex items-center justify-between bg-surface border border-border rounded px-3 py-2">
            <div className="flex-1">
              <p className="text-sm text-text-primary">{e.bio.slice(0, 80)}{e.bio.length > 80 ? "..." : ""}</p>
              <div className="flex gap-1 mt-1 flex-wrap">
                {e.industries.map((i) => (
                  <span key={i.id} className="text-xs border border-border text-text-secondary px-1.5 py-0.5 rounded">{i.name}</span>
                ))}
                {e.skills.map((s) => (
                  <span key={s.id} className="text-xs border border-border text-text-tertiary px-1.5 py-0.5 rounded">{s.name}</span>
                ))}
              </div>
            </div>
            <button
              onClick={() => handleAssign(e.id)}
              disabled={assigning === e.id}
              className="ml-3 px-3 py-1 text-xs bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 transition"
            >
              {assigning === e.id ? "..." : "Assign"}
            </button>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-sm text-text-tertiary text-center py-4">No matching experts</p>
        )}
      </div>
    </div>
  );
}
