"use client";

import { useEffect, useMemo, useState } from "react";
import { TeamOut } from "@/lib/api";
import { api } from "@/lib/api.client";
import { FdrChip, Note, SectionTitle, StrengthBar } from "@/components/ui";

type SortKey = "total" | "name" | "attack" | "defence";

const SCORE: Record<SortKey, (t: TeamOut) => number | string> = {
  total: (t) =>
    (t.strength_attack_home ?? 0) +
    (t.strength_attack_away ?? 0) +
    (t.strength_defence_home ?? 0) +
    (t.strength_defence_away ?? 0),
  name: (t) => t.name,
  attack: (t) => (t.strength_attack_home ?? 0) + (t.strength_attack_away ?? 0),
  defence: (t) => (t.strength_defence_home ?? 0) + (t.strength_defence_away ?? 0),
};

export default function TeamsPage() {
  const [teams, setTeams] = useState<TeamOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("total");
  const [dir, setDir] = useState<1 | -1>(-1);

  useEffect(() => {
    api
      .teams()
      .then(setTeams)
      .catch((e) => setError(String(e)));
  }, []);

  // Attack and defence are scaled against their own maxima: FPL rates overall
  // strength 1-5 but attack/defence in the 1000-1400 range, so one shared
  // scale would make every bar meaningless.
  const maxAtt = useMemo(
    () =>
      Math.max(
        1,
        ...(teams ?? []).flatMap((t) => [
          t.strength_attack_home ?? 0,
          t.strength_attack_away ?? 0,
        ]),
      ),
    [teams],
  );
  const maxDef = useMemo(
    () =>
      Math.max(
        1,
        ...(teams ?? []).flatMap((t) => [
          t.strength_defence_home ?? 0,
          t.strength_defence_away ?? 0,
        ]),
      ),
    [teams],
  );

  const rows = useMemo(() => {
    if (!teams) return [];
    const needle = q.trim().toLowerCase();
    const fn = SCORE[sort];
    return teams
      .filter((t) => !needle || t.name.toLowerCase().includes(needle))
      .slice()
      .sort((a, b) => {
        const av = fn(a);
        const bv = fn(b);
        return (av > bv ? 1 : av < bv ? -1 : 0) * dir;
      });
  }, [teams, q, sort, dir]);

  return (
    <div>
      <SectionTitle n={1}>Team strength (FPL ratings, home / away)</SectionTitle>
      <Note>
        FPL&apos;s own attack and defence ratings per club, split home and away and
        independent of any particular opponent. They are the basis of fixture difficulty.
        The API serves these as zeroes before a season starts, so the pipeline backfills
        each one from the club&apos;s most recent season — and for a promoted side, from
        the previous season&apos;s league average.
      </Note>

      {error ? (
        <div className="rounded-[10px] border border-dashed border-hairline bg-surface p-9 text-center text-[13.5px] text-ink-2">
          Could not reach the API — is the backend running on port 8000?
        </div>
      ) : (
        <div className="rounded-[10px] border border-hairline bg-surface p-5">
          <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search club…"
              aria-label="Search club"
              className="min-w-[180px] flex-1 rounded-md border border-hairline bg-surface px-3 py-2 text-[13px] placeholder:text-ink-3"
            />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              aria-label="Sort clubs"
              className="rounded-md border border-hairline bg-surface px-3 py-2 text-[13px]"
            >
              <option value="total">Sort: total</option>
              <option value="name">Sort: name</option>
              <option value="attack">Sort: attack</option>
              <option value="defence">Sort: defence</option>
            </select>
            <button
              onClick={() => setDir((d) => (d === 1 ? -1 : 1))}
              className="rounded-md bg-pitch px-3 py-2 text-xs font-bold text-white"
            >
              {dir === -1 ? "↓ descending" : "↑ ascending"}
            </button>
          </div>

          {teams === null ? (
            <p className="py-6 text-center text-[13.5px] text-ink-2">Loading…</p>
          ) : (
            rows.map((t) => (
              <div
                key={t.code}
                className="grid grid-cols-1 items-center gap-3.5 border-t border-hairline py-2.5 first:border-t-0 sm:grid-cols-[150px_1fr_1fr]"
              >
                <div>
                  <div className="text-[13px] font-semibold">{t.name}</div>
                  {t.next_opponent && (
                    <div className="mt-1">
                      {/* the chip appends its own H/A marker */}
                      <FdrChip
                        difficulty={t.next_fdr}
                        label={t.next_opponent.replace(/\s*\((H|A)\)/g, "")}
                        home={t.next_opponent.includes("(H)")}
                      />
                    </div>
                  )}
                </div>
                <StrengthBar
                  variant="att"
                  label={`Attack (H ${t.strength_attack_home ?? "—"} / A ${t.strength_attack_away ?? "—"})`}
                  value={
                    ((t.strength_attack_home ?? 0) + (t.strength_attack_away ?? 0)) / 2
                  }
                  max={maxAtt}
                />
                <StrengthBar
                  variant="def"
                  label={`Defence (H ${t.strength_defence_home ?? "—"} / A ${t.strength_defence_away ?? "—"})`}
                  value={
                    ((t.strength_defence_home ?? 0) + (t.strength_defence_away ?? 0)) / 2
                  }
                  max={maxDef}
                />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
