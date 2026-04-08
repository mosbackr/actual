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
      <h3 className="text-lg font-medium">Expert Assignments</h3>

      {assignments.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-gray-400">Assigned:</p>
          {assignments.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-gray-900 rounded px-3 py-2">
              <span className="text-sm">
                Expert {a.expert_id.slice(0, 8)}... —{" "}
                <span className={a.status === "accepted" ? "text-emerald-400" : a.status === "declined" ? "text-red-400" : "text-yellow-400"}>
                  {a.status}
                </span>
              </span>
              <button
                onClick={() => onRemoveAssignment(a.id)}
                className="text-xs text-red-400 hover:text-red-300"
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
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white"
        />
      </div>

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {filtered.map((e) => (
          <div key={e.id} className="flex items-center justify-between bg-gray-900/50 rounded px-3 py-2">
            <div className="flex-1">
              <p className="text-sm text-white">{e.bio.slice(0, 80)}{e.bio.length > 80 ? "..." : ""}</p>
              <div className="flex gap-1 mt-1 flex-wrap">
                {e.industries.map((i) => (
                  <span key={i.id} className="text-xs bg-blue-900 text-blue-300 px-1.5 py-0.5 rounded">{i.name}</span>
                ))}
                {e.skills.map((s) => (
                  <span key={s.id} className="text-xs bg-purple-900 text-purple-300 px-1.5 py-0.5 rounded">{s.name}</span>
                ))}
              </div>
            </div>
            <button
              onClick={() => handleAssign(e.id)}
              disabled={assigning === e.id}
              className="ml-3 px-3 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              {assigning === e.id ? "..." : "Assign"}
            </button>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-sm text-gray-500 text-center py-4">No matching experts</p>
        )}
      </div>
    </div>
  );
}
