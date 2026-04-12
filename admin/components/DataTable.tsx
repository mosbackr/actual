"use client";

import { useState } from "react";

interface Column<T> {
  key: string;
  label: string;
  render?: (item: T) => React.ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyField: string;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  keyField,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const sorted = [...data].sort((a, b) => {
    if (!sortKey) return 0;
    const aVal = String(a[sortKey] ?? "");
    const bVal = String(b[sortKey] ?? "");
    return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  });

  function handleSort(key: string) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => handleSort(col.key)}
                className="text-left px-3 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium cursor-pointer hover:text-text-primary transition"
              >
                {col.label}
                {sortKey === col.key && (sortAsc ? " \u2191" : " \u2193")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((item) => (
            <tr
              key={String(item[keyField])}
              className="border-b border-border hover:bg-hover-row transition-colors"
            >
              {columns.map((col) => (
                <td key={col.key} className="px-3 py-4">
                  {col.render ? col.render(item) : String(item[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.length === 0 && (
        <p className="text-center text-text-tertiary py-8">No data</p>
      )}
    </div>
  );
}
