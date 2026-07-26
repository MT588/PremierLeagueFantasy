"use client";

import { useMemo, useState } from "react";
import { Column, columnValue } from "@/components/DataTable";

export interface FilterableRow {
  web_name: string;
  full_name: string;
  team_short: string | null;
  position: number;
}

export interface NumFilter {
  field: string;
  min: number | null;
  max: number | null;
}

export interface FilterState {
  q: string;
  setQ: (v: string) => void;
  positions: Set<number>;
  togglePosition: (p: number) => void;
  teams: Set<string>;
  addTeam: (t: string) => void;
  removeTeam: (t: string) => void;
  nums: NumFilter[];
  addNum: () => void;
  updateNum: (i: number, patch: Partial<NumFilter>) => void;
  removeNum: (i: number) => void;
  clear: () => void;
  allTeams: string[];
  numericColumns: { key: string; label: string }[];
}

/** One filter engine for every table: free-text search, position chips, club
 *  chips, and any number of stacked min/max filters on the table's own numeric
 *  columns. The numeric picker is built from the column definitions, so a table
 *  that gains a column automatically gains a filter for it. */
export function useTableFilters<T extends FilterableRow>(
  rows: T[],
  columns: Column<T>[],
): { filtered: T[]; state: FilterState } {
  const [q, setQ] = useState("");
  const [positions, setPositions] = useState<Set<number>>(new Set());
  const [teams, setTeams] = useState<Set<string>>(new Set());
  const [nums, setNums] = useState<NumFilter[]>([]);

  const numericColumns = useMemo(
    () => columns.filter((c) => c.numeric).map((c) => ({ key: c.key, label: c.label })),
    [columns],
  );

  const allTeams = useMemo(
    () =>
      [...new Set(rows.map((r) => r.team_short).filter((t): t is string => !!t))].sort(),
    [rows],
  );

  const colByKey = useMemo(
    () => new Map(columns.map((c) => [c.key, c])),
    [columns],
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (needle) {
        const hit =
          r.web_name.toLowerCase().includes(needle) ||
          r.full_name.toLowerCase().includes(needle) ||
          (r.team_short ?? "").toLowerCase().includes(needle);
        if (!hit) return false;
      }
      if (positions.size && !positions.has(r.position)) return false;
      if (teams.size && !(r.team_short && teams.has(r.team_short))) return false;
      for (const n of nums) {
        if (n.min === null && n.max === null) continue;
        const col = colByKey.get(n.field);
        const raw = col ? columnValue(col, r) : (r as Record<string, unknown>)[n.field];
        // A row with no value for the filtered column cannot satisfy a bound.
        if (raw === null || raw === undefined) return false;
        const v = Number(raw);
        if (Number.isNaN(v)) return false;
        if (n.min !== null && !(v >= n.min)) return false;
        if (n.max !== null && !(v <= n.max)) return false;
      }
      return true;
    });
  }, [rows, q, positions, teams, nums, colByKey]);

  const state: FilterState = {
    q,
    setQ,
    positions,
    togglePosition: (p) =>
      setPositions((prev) => {
        const next = new Set(prev);
        if (next.has(p)) next.delete(p);
        else next.add(p);
        return next;
      }),
    teams,
    addTeam: (t) => setTeams((prev) => new Set(prev).add(t)),
    removeTeam: (t) =>
      setTeams((prev) => {
        const next = new Set(prev);
        next.delete(t);
        return next;
      }),
    nums,
    addNum: () =>
      setNums((prev) =>
        numericColumns.length
          ? [...prev, { field: numericColumns[0].key, min: null, max: null }]
          : prev,
      ),
    updateNum: (i, patch) =>
      setNums((prev) => prev.map((n, j) => (j === i ? { ...n, ...patch } : n))),
    removeNum: (i) => setNums((prev) => prev.filter((_, j) => j !== i)),
    clear: () => {
      setQ("");
      setPositions(new Set());
      setTeams(new Set());
      setNums([]);
    },
    allTeams,
    numericColumns,
  };

  return { filtered, state };
}
