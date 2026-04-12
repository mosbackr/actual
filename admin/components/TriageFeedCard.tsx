"use client";

import Link from "next/link";
import { StatusBadge } from "./StatusBadge";
import type { TriageItem, PipelineStartup, ExpertApplication, Assignment } from "@/lib/types";

interface TriageFeedCardProps {
  item: TriageItem;
  onApproveStartup?: (id: string) => void;
  onRejectStartup?: (id: string) => void;
  onApproveExpert?: (id: string) => void;
  onRejectExpert?: (id: string) => void;
}

const TYPE_LABELS: Record<string, string> = {
  startup: "Startup",
  expert_application: "Expert App",
  assignment: "Assignment",
};

export function TriageFeedCard({
  item,
  onApproveStartup,
  onRejectStartup,
  onApproveExpert,
  onRejectExpert,
}: TriageFeedCardProps) {
  const timeAgo = new Date(item.timestamp).toLocaleDateString();

  return (
    <div className="border border-border rounded p-4 hover:border-text-tertiary transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs px-2 py-0.5 rounded border border-border font-medium text-text-secondary">
          {TYPE_LABELS[item.type]}
        </span>
        <span className="text-xs text-text-tertiary">{timeAgo}</span>
      </div>

      {item.type === "startup" && renderStartup(item.data as PipelineStartup, onApproveStartup, onRejectStartup)}
      {item.type === "expert_application" && renderExpert(item.data as ExpertApplication, onApproveExpert, onRejectExpert)}
      {item.type === "assignment" && renderAssignment(item.data as Assignment)}
    </div>
  );
}

function renderStartup(
  s: PipelineStartup,
  onApprove?: (id: string) => void,
  onReject?: (id: string) => void,
) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <Link href={`/startups/${s.id}`} className="font-medium text-text-primary hover:text-accent transition">
          {s.name}
        </Link>
        <StatusBadge status={s.status} />
      </div>
      <p className="text-sm text-text-secondary mt-1 line-clamp-2">{s.description}</p>
      <div className="flex items-center gap-2 mt-2 text-xs text-text-tertiary">
        <span>{s.stage}</span>
        {s.industries.map((i) => (
          <span key={i.id} className="border border-border px-1.5 py-0.5 rounded">{i.name}</span>
        ))}
      </div>
      {s.status === "pending" && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => onApprove?.(s.id)}
            className="px-3 py-1 text-xs bg-score-high text-white rounded hover:opacity-90 transition"
          >
            Approve
          </button>
          <button
            onClick={() => onReject?.(s.id)}
            className="px-3 py-1 text-xs bg-score-low text-white rounded hover:opacity-90 transition"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

function renderExpert(
  e: ExpertApplication,
  onApprove?: (id: string) => void,
  onReject?: (id: string) => void,
) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <Link href={`/experts/${e.id}`} className="font-medium text-text-primary hover:text-accent transition">
          Expert Application
        </Link>
        <StatusBadge status={e.application_status} />
      </div>
      <p className="text-sm text-text-secondary mt-1">{e.bio}</p>
      <p className="text-xs text-text-tertiary mt-1">{e.years_experience} years experience</p>
      {e.application_status === "pending" && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => onApprove?.(e.id)}
            className="px-3 py-1 text-xs bg-score-high text-white rounded hover:opacity-90 transition"
          >
            Approve
          </button>
          <button
            onClick={() => onReject?.(e.id)}
            className="px-3 py-1 text-xs bg-score-low text-white rounded hover:opacity-90 transition"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

function renderAssignment(a: Assignment) {
  return (
    <div>
      <p className="text-sm text-text-primary">
        Assignment <StatusBadge status={a.status} />
      </p>
      <p className="text-xs text-text-tertiary mt-1">
        Expert responded: {a.responded_at ? new Date(a.responded_at).toLocaleDateString() : "pending"}
      </p>
    </div>
  );
}
