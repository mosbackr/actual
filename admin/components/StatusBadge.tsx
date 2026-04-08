const COLORS: Record<string, string> = {
  pending: "bg-yellow-900 text-yellow-300",
  approved: "bg-emerald-900 text-emerald-300",
  rejected: "bg-red-900 text-red-300",
  featured: "bg-indigo-900 text-indigo-300",
  accepted: "bg-emerald-900 text-emerald-300",
  declined: "bg-red-900 text-red-300",
};

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] || "bg-gray-800 text-gray-300";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
