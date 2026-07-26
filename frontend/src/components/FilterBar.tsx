"use client";

import { FilterState } from "@/lib/useTableFilters";
import { POSITIONS } from "@/lib/ui";

const inputCls =
  "rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink";

export function FilterBar({
  state,
  shown,
  total,
}: {
  state: FilterState;
  shown: number;
  total: number;
}) {
  return (
    <div className="mb-2.5 rounded-[10px] border border-hairline bg-surface px-3 py-2.5">
      {/* search + positions */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={state.q}
          onChange={(e) => state.setQ(e.target.value)}
          placeholder="Search name or club…"
          aria-label="Search name or club"
          className={`${inputCls} min-w-[150px] flex-1 placeholder:text-ink-3`}
        />
        <span className="text-[10.5px] font-bold uppercase tracking-[0.07em] text-ink-2">
          Position
        </span>
        {[1, 2, 3, 4].map((p) => {
          const on = state.positions.has(p);
          return (
            <button
              key={p}
              onClick={() => state.togglePosition(p)}
              aria-pressed={on}
              className={`rounded-full border px-3 py-1 text-xs ${
                on
                  ? "border-pitch bg-pitch text-white"
                  : "border-hairline bg-surface text-ink"
              }`}
            >
              {POSITIONS[p]}
            </button>
          );
        })}
        <button
          onClick={state.clear}
          className="rounded-md border border-hairline px-3 py-1.5 text-xs font-bold text-ink-2"
        >
          Clear
        </button>
      </div>

      {/* clubs */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[10.5px] font-bold uppercase tracking-[0.07em] text-ink-2">
          Clubs
        </span>
        <select
          value=""
          onChange={(e) => e.target.value && state.addTeam(e.target.value)}
          aria-label="Add a club filter"
          className={inputCls}
        >
          <option value="">+ add club</option>
          {state.allTeams
            .filter((t) => !state.teams.has(t))
            .map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
        </select>
        {[...state.teams].map((t) => (
          <button
            key={t}
            onClick={() => state.removeTeam(t)}
            className="rounded-full border border-[#CFE0D6] bg-[#EEF4F0] px-3 py-1 text-xs"
          >
            {t}
            <span className="ml-1.5 font-bold text-ink-2" aria-hidden>
              ×
            </span>
            <span className="sr-only">remove club filter</span>
          </button>
        ))}
      </div>

      {/* stacked numeric column filters */}
      {state.nums.map((n, i) => (
        <div key={i} className="mb-2 flex flex-wrap items-center gap-1.5">
          <select
            value={n.field}
            onChange={(e) => state.updateNum(i, { field: e.target.value })}
            aria-label="Filter column"
            className={inputCls}
          >
            {state.numericColumns.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
          <span className="text-[10.5px] font-bold uppercase tracking-[0.07em] text-ink-2">
            from
          </span>
          <input
            type="number"
            step="any"
            value={n.min ?? ""}
            onChange={(e) =>
              state.updateNum(i, {
                min: e.target.value === "" ? null : parseFloat(e.target.value),
              })
            }
            aria-label="Minimum"
            className={`${inputCls} w-20`}
          />
          <span className="text-[10.5px] font-bold uppercase tracking-[0.07em] text-ink-2">
            to
          </span>
          <input
            type="number"
            step="any"
            value={n.max ?? ""}
            onChange={(e) =>
              state.updateNum(i, {
                max: e.target.value === "" ? null : parseFloat(e.target.value),
              })
            }
            aria-label="Maximum"
            className={`${inputCls} w-20`}
          />
          <button
            onClick={() => state.removeNum(i)}
            className="rounded-md border border-hairline px-2.5 py-1.5 text-xs font-bold text-ink-2"
          >
            remove
          </button>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={state.addNum}
          className="rounded-md bg-pitch-light px-3 py-1.5 text-xs font-bold text-white"
        >
          + column filter
        </button>
        <span className="ml-auto text-xs text-ink-2">
          {shown} of {total} players
        </span>
      </div>
    </div>
  );
}
