"use client";

import { useEffect, useState } from "react";
import { PlayerStats } from "@/lib/api";
import { api } from "@/lib/api.client";
import { useTableFilters } from "@/lib/useTableFilters";
import { Column, DataTable } from "@/components/DataTable";
import { FilterBar } from "@/components/FilterBar";
import { SectionTitle } from "@/components/ui";

/** Every stat view is the same shape: a titled section, some methodology copy,
 *  the shared filter bar, and one sortable table over /api/player-stats. */
export function StatsPage({
  n,
  title,
  intro,
  columns,
  prefilter,
  initialSort,
  limit,
  footer,
}: {
  n: number;
  title: string;
  intro?: React.ReactNode;
  columns: Column<PlayerStats>[];
  /** Rows excluded before filtering, e.g. players ruled out of the next match. */
  prefilter?: (p: PlayerStats) => boolean;
  initialSort?: { key: string; dir?: 1 | -1 };
  limit?: number;
  footer?: React.ReactNode;
}) {
  const [all, setAll] = useState<PlayerStats[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .playerStats()
      .then(setAll)
      .catch((e) => setError(String(e)));
  }, []);

  const base = all ? (prefilter ? all.filter(prefilter) : all) : [];
  const { filtered, state } = useTableFilters(base, columns);
  const season = all?.find((p) => p.stat_season)?.stat_season;

  return (
    <div>
      <SectionTitle
        n={n}
        aside={season ? `season figures from ${season}` : undefined}
      >
        {title}
      </SectionTitle>
      {intro}
      {error ? (
        <div className="rounded-[10px] border border-dashed border-hairline bg-surface p-9 text-center text-[13.5px] text-ink-2">
          Could not reach the API — is the backend running on port 8000?
          <div className="mt-1 text-xs">{error}</div>
        </div>
      ) : all === null ? (
        <div className="rounded-[10px] border border-dashed border-hairline bg-surface p-9 text-center text-[13.5px] text-ink-2">
          Loading…
        </div>
      ) : (
        <>
          <FilterBar state={state} shown={filtered.length} total={base.length} />
          <DataTable
            columns={columns}
            rows={filtered}
            rowKey={(p) => p.code}
            initialSort={initialSort}
            limit={limit}
          />
          {footer}
        </>
      )}
    </div>
  );
}
