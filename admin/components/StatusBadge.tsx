const COLORS: Record<string, string> = {
  pending: "text-score-mid border-score-mid/30",
  approved: "text-score-high border-score-high/30",
  rejected: "text-score-low border-score-low/30",
  featured: "text-accent border-accent/30",
  accepted: "text-score-high border-score-high/30",
  declined: "text-score-low border-score-low/30",
};

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] || "text-text-tertiary border-border";
  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
