"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { OptimalTeam, SquadPlayer } from "@/lib/api";
import { api } from "@/lib/api.client";
import { fmtPrice } from "@/lib/ui";
import { Card, SectionTitle } from "@/components/ui";

function PlayerCard({ p }: { p: SquadPlayer }) {
  return (
    <Link
      href={`/players/${p.code}`}
      className="relative flex w-24 flex-col items-center rounded-lg border border-hairline bg-surface/90 px-2 py-2 text-center shadow-sm transition-colors hover:border-accent sm:w-28"
    >
      {p.is_captain && (
        <span
          className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-white"
          title="captain"
        >
          C
        </span>
      )}
      <span className="w-full truncate text-xs font-medium sm:text-sm">{p.web_name}</span>
      <span className="text-[10px] text-ink-3">
        {p.team_short} · {fmtPrice(p.price)}
      </span>
      <span className="mt-0.5 text-xs font-semibold tabular-nums text-accent">
        {p.predicted_points.toFixed(1)}
      </span>
    </Link>
  );
}

export default function TeamPage() {
  const [budget, setBudget] = useState(100);
  const [horizon, setHorizon] = useState(1);
  const [team, setTeam] = useState<OptimalTeam | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .optimalTeam(budget, horizon)
        .then(setTeam)
        .catch((e) => setError(String(e)))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [budget, horizon]);

  const rows = team
    ? [1, 2, 3, 4].map((pos) => team.starting_xi.filter((p) => p.position === pos))
    : [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <SectionTitle n={2}>Optimal team</SectionTitle>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2 text-ink-2">
            Budget
            <input
              type="range"
              min={80}
              max={110}
              step={0.5}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
              className="accent-pitch"
            />
            <span className="w-16 tabular-nums">{fmtPrice(budget)}</span>
          </label>
          <label className="flex items-center gap-2 text-ink-2">
            Horizon
            <select
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              className="rounded-lg border border-hairline bg-surface px-2 py-1.5"
            >
              {[1, 2, 3, 4, 5].map((h) => (
                <option key={h} value={h}>
                  {h} GW{h > 1 ? "s" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <Card>Failed to optimize — is the API running? {error}</Card>}

      {team && !error && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <div className="text-xs uppercase tracking-wide text-ink-3">Expected points</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">
                {team.expected_points.toFixed(1)}
              </div>
              <div className="mt-1 text-xs text-ink-3">
                XI + captain, GW{team.gameweeks[0]}
                {team.gameweeks.length > 1 && `–${team.gameweeks[team.gameweeks.length - 1]}`}
              </div>
            </Card>
            <Card>
              <div className="text-xs uppercase tracking-wide text-ink-3">Squad cost</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">
                {fmtPrice(team.total_cost)}
              </div>
              <div className="mt-1 text-xs text-ink-3">of {fmtPrice(team.budget)} budget</div>
            </Card>
            <Card>
              <div className="text-xs uppercase tracking-wide text-ink-3">Rules</div>
              <div className="mt-1 text-sm text-ink-2">
                15 players · 2 GK / 5 DEF / 5 MID / 3 FWD · max 3 per club · legal formation
              </div>
            </Card>
          </div>

          <div
            className={`relative rounded-xl border border-hairline bg-gradient-to-b from-[#0B3D2E] to-[#14543F] px-2 py-6 transition-opacity ${loading ? "opacity-50" : ""}`}
          >
            <div className="pointer-events-none absolute inset-x-8 top-1/2 h-px bg-white/10" />
            <div className="pointer-events-none absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/10" />
            <div className="relative space-y-6">
              {rows.map((row, i) => (
                <div key={i} className="flex flex-wrap justify-center gap-2 sm:gap-4">
                  {row.map((p) => (
                    <PlayerCard key={p.code} p={p} />
                  ))}
                </div>
              ))}
            </div>
          </div>

          <Card title="Bench">
            <div className="flex flex-wrap gap-2 sm:gap-4">
              {team.bench.map((p) => (
                <PlayerCard key={p.code} p={p} />
              ))}
            </div>
          </Card>
        </>
      )}

      {loading && !team && <Card>Solving…</Card>}
    </div>
  );
}
