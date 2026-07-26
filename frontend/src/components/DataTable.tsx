"use client";

import { useMemo, useState } from "react";

export interface Column<T> {
  /** Field name; doubles as the sort key and the numeric-filter identifier. */
  key: string;
  label: string;
  /** Right-aligned, tabular figures, and offered in the numeric filter picker. */
  numeric?: boolean;
  /** Hidden below 760px — still reachable by scrolling the table sideways. */
  optional?: boolean;
  sortable?: boolean;
  /** Sort/filter value. Defaults to `row[key]`. */
  get?: (row: T) => number | string | null;
  render: (row: T, index: number) => React.ReactNode;
}

export function columnValue<T>(col: Column<T>, row: T): number | string | null {
  if (col.get) return col.get(row);
  const v = (row as Record<string, unknown>)[col.key];
  return v === undefined ? null : (v as number | string | null);
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  initialSort,
  limit,
  empty = "No players match these filters.",
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  initialSort?: { key: string; dir?: 1 | -1 };
  limit?: number;
  empty?: string;
}) {
  const [sortKey, setSortKey] = useState(initialSort?.key ?? columns[0].key);
  const [sortDir, setSortDir] = useState<1 | -1>(initialSort?.dir ?? -1);

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return rows;
    // Nulls always sink to the bottom, whichever way the column is sorted —
    // a missing stat is never "the best" or "the worst" result.
    return [...rows].sort((a, b) => {
      const av = columnValue(col, a);
      const bv = columnValue(col, b);
      const an = av === null || av === undefined;
      const bn = bv === null || bv === undefined;
      if (an && bn) return 0;
      if (an) return 1;
      if (bn) return -1;
      return (av > bv ? 1 : av < bv ? -1 : 0) * sortDir;
    });
  }, [rows, columns, sortKey, sortDir]);

  const shown = limit ? sorted.slice(0, limit) : sorted;

  const onSort = (col: Column<T>) => {
    if (col.sortable === false) return;
    if (sortKey === col.key) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(col.key);
      setSortDir(-1);
    }
  };

  return (
    <div className="sticky-name mb-2 overflow-x-auto rounded-[10px] border border-hairline">
      <table className="w-full border-collapse bg-surface">
        <thead>
          <tr>
            {columns.map((col) => {
              const active = sortKey === col.key;
              const sortable = col.sortable !== false;
              return (
                <th
                  key={col.key}
                  onClick={() => onSort(col)}
                  aria-sort={
                    active ? (sortDir === 1 ? "ascending" : "descending") : undefined
                  }
                  className={`whitespace-nowrap bg-pitch px-3 py-2.5 text-[11px] font-bold uppercase tracking-[0.05em] text-white select-none ${
                    col.numeric ? "text-right" : "text-left"
                  } ${col.optional ? "col-opt" : ""} ${
                    sortable ? "cursor-pointer hover:bg-pitch-light" : ""
                  }`}
                >
                  {col.label}
                  {active && (
                    <span className="ml-1 text-gold" aria-hidden>
                      {sortDir === 1 ? "↑" : "↓"}
                    </span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-10 text-center text-[13.5px] text-ink-2"
              >
                {empty}
              </td>
            </tr>
          ) : (
            shown.map((row, i) => (
              <tr key={rowKey(row)} className="hover:bg-[#FAF8F1]">
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`whitespace-nowrap border-t border-hairline px-3 py-2 text-[13px] ${
                      col.numeric ? "text-right tabular-nums" : ""
                    } ${col.optional ? "col-opt" : ""}`}
                  >
                    {col.render(row, i)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
