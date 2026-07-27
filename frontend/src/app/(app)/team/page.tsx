"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { GameweekPlan, OptimalPlan, SquadPlayer, TransferPlayer } from "@/lib/api";
import { api } from "@/lib/api.client";
import { fmtPrice } from "@/lib/ui";
import { Card, SectionTitle } from "@/components/ui";

const HORIZONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

type Move = "in" | "promoted" | "demoted";

const MOVE_BADGE: Record<Move, { label: string; cls: string; title: string }> = {
  in: { label: "IN", cls: "bg-[#E08B3D] text-white", title: "transferred in this gameweek" },
  promoted: { label: "↑", cls: "bg-[#3E8E5A] text-white", title: "up from the bench" },
  demoted: { label: "↓", cls: "bg-[#C0392B] text-white", title: "down to the bench" },
};

type Swap = { out: TransferPlayer; incoming: TransferPlayer };

type WeekChanges = {
  transfers: Swap[];
  promoted: SquadPlayer[];
  demoted: SquadPlayer[];
  arrivals: Set<number>;
  quiet: boolean;
};

/** What this week does differently from the one before it. */
function changesFor(week: GameweekPlan, previous: GameweekPlan | null): WeekChanges {
  // transfers_in and transfers_out are equal in length and both ordered by
  // position, so the player at the same index is the like-for-like replacement.
  const transfers = week.transfers_out
    .map((out, i) => ({ out, incoming: week.transfers_in[i] }))
    .filter((swap): swap is Swap => Boolean(swap.incoming));
  const arrivals = new Set(week.transfers_in.map((p) => p.code));

  if (!previous) {
    return { transfers, promoted: [], demoted: [], arrivals, quiet: false };
  }
  const previousXi = new Set(previous.starting_xi.map((p) => p.code));
  const promoted = week.starting_xi.filter(
    (p) => !previousXi.has(p.code) && !arrivals.has(p.code),
  );
  const demoted = week.bench.filter((p) => previousXi.has(p.code));
  return {
    transfers,
    promoted,
    demoted,
    arrivals,
    quiet: !transfers.length && !promoted.length && !demoted.length,
  };
}

function PlayerCard({ p, move }: { p: SquadPlayer; move?: Move }) {
  const badge = move ? MOVE_BADGE[move] : null;
  return (
    <Link
      href={`/players/${p.code}`}
      // Prefetching 404s in production — see Sidebar.tsx.
      prefetch={false}
      className="relative flex w-24 flex-col items-center rounded-lg border border-hairline bg-surface/90 px-2 py-2 text-center shadow-sm transition-colors hover:border-accent sm:w-28"
    >
      {/* Gold, not the accent green — the pitch behind it is that same green. */}
      {p.is_captain && (
        <span
          className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-gold text-[10px] font-bold text-ink"
          title="captain"
        >
          C
        </span>
      )}
      {badge && (
        <span
          className={`absolute -top-2 -left-2 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1 text-[10px] font-bold ${badge.cls}`}
          title={badge.title}
        >
          {badge.label}
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

/** Every change across the horizon, so one screenshot carries the whole plan. */
function PlanLog({
  plan,
  changes,
  active,
  onSelect,
}: {
  plan: OptimalPlan;
  changes: WeekChanges[];
  active: number;
  onSelect: (i: number) => void;
}) {
  const moves = changes.reduce((n, c) => n + c.transfers.length, 0);
  return (
    <Card title={`Plan · ${plan.weeks.length} GWs · ${moves} transfer${moves === 1 ? "" : "s"}`}>
      <ol className="space-y-1.5">
        {plan.weeks.map((w, i) => {
          const c = changes[i];
          return (
            <li key={w.gameweek}>
              <button
                type="button"
                onClick={() => onSelect(i)}
                className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                  i === active
                    ? "border-pitch bg-[#EEF4F0]"
                    : "border-transparent hover:border-hairline"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-semibold">GW{w.gameweek}</span>
                  <span className="text-xs tabular-nums text-ink-2">
                    {w.expected_points.toFixed(1)} pts
                    {w.bank_before !== null && ` · ${w.bank_after} banked`}
                  </span>
                </div>

                {c.transfers.map(({ out, incoming }) => (
                  <div key={out.code} className="mt-1 flex flex-wrap items-baseline gap-1 text-xs">
                    <span className="font-bold text-[#C0392B]">OUT</span>
                    <span>{out.web_name}</span>
                    <span className="text-ink-3">→</span>
                    <span className="font-bold text-[#3E8E5A]">IN</span>
                    <span className="font-medium">{incoming.web_name}</span>
                  </div>
                ))}

                {(c.promoted.length > 0 || c.demoted.length > 0) && (
                  <div className="mt-1 flex flex-wrap gap-x-2 text-xs text-ink-2">
                    {c.promoted.map((p) => (
                      <span key={p.code}>
                        <span className="font-bold text-[#3E8E5A]">↑</span> {p.web_name}
                      </span>
                    ))}
                    {c.demoted.map((p) => (
                      <span key={p.code}>
                        <span className="font-bold text-[#C0392B]">↓</span> {p.web_name}
                      </span>
                    ))}
                  </div>
                )}

                {i === 0 && (
                  <div className="mt-1 text-xs text-ink-3">opening squad</div>
                )}
                {c.quiet && i > 0 && (
                  <div className="mt-1 text-xs text-ink-3">unchanged</div>
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export default function TeamPage() {
  const [budget, setBudget] = useState(100);
  const [horizon, setHorizon] = useState(5);
  const [plan, setPlan] = useState<OptimalPlan | null>(null);
  const [activeWeek, setActiveWeek] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // A ten-gameweek solve takes the better part of a minute, so wait longer
    // before firing one and ignore anything that lands after the inputs moved
    // on — otherwise a slow earlier solve overwrites a newer, faster one.
    let stale = false;
    const t = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .optimalTeam(budget, horizon)
        .then((next) => {
          if (stale) return;
          setPlan(next);
          // Nudging the budget shouldn't throw you back to the first gameweek,
          // but a shorter horizon can leave the selected week out of range.
          setActiveWeek((w) => Math.min(w, Math.max(next.weeks.length - 1, 0)));
        })
        .catch((e) => {
          if (!stale) setError(String(e));
        })
        .finally(() => {
          if (!stale) setLoading(false);
        });
    }, horizon > 5 ? 800 : 300);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [budget, horizon]);

  const index = plan ? Math.min(activeWeek, Math.max(plan.weeks.length - 1, 0)) : 0;
  const week = plan?.weeks[index] ?? null;
  const changes = plan
    ? plan.weeks.map((w, i) => changesFor(w, i > 0 ? plan.weeks[i - 1] : null))
    : [];
  const change = changes[index] ?? null;

  function moveFor(p: SquadPlayer, inXi: boolean): Move | undefined {
    if (!change) return undefined;
    if (change.arrivals.has(p.code)) return "in";
    if (inXi && change.promoted.some((q) => q.code === p.code)) return "promoted";
    if (!inXi && change.demoted.some((q) => q.code === p.code)) return "demoted";
    return undefined;
  }

  const rows = week
    ? [1, 2, 3, 4].map((pos) => week.starting_xi.filter((p) => p.position === pos))
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
              {HORIZONS.map((h) => (
                <option key={h} value={h}>
                  {h} GW{h > 1 ? "s" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <Card>Failed to optimize — is the API running? {error}</Card>}

      {plan && week && !error && (
        <>
          {plan.weeks.length < horizon && (
            <Card>
              Only {plan.weeks.length} gameweek{plan.weeks.length === 1 ? " has" : "s have"}{" "}
              predictions so far — planning over GW{plan.weeks[0].gameweek}–
              {plan.weeks[plan.weeks.length - 1].gameweek}. Run{" "}
              <code>ml.predict_v3 --horizon {horizon}</code> to go further out.
            </Card>
          )}

          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <div className="text-xs uppercase tracking-wide text-ink-3">Expected points</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">
                {plan.total_expected_points.toFixed(1)}
              </div>
              <div className="mt-1 text-xs text-ink-3">
                XI + captain over {plan.weeks.length} GW
                {plan.weeks.length === 1 ? "" : "s"} · {week.expected_points.toFixed(1)} in
                GW{week.gameweek}
              </div>
            </Card>
            <Card>
              <div className="text-xs uppercase tracking-wide text-ink-3">Squad cost</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">
                {fmtPrice(week.total_cost)}
              </div>
              <div className="mt-1 text-xs text-ink-3">of {fmtPrice(plan.budget)} budget</div>
            </Card>
            <Card>
              <div className="text-xs uppercase tracking-wide text-ink-3">Free transfers</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">
                {week.bank_before === null ? "—" : week.bank_before}
              </div>
              <div className="mt-1 text-xs text-ink-3">
                {week.bank_before === null
                  ? "opening squad is a free pick"
                  : `${week.transfers_used} used · ${week.bank_after} banked, max 5`}
              </div>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="space-y-4">
              <div
                className={`relative rounded-xl border border-hairline bg-gradient-to-b from-[#0B3D2E] to-[#14543F] px-2 py-6 transition-opacity ${loading ? "opacity-50" : ""}`}
              >
                <div className="pointer-events-none absolute inset-x-8 top-1/2 h-px bg-white/10" />
                <div className="pointer-events-none absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/10" />
                <span className="absolute left-4 top-3 text-xs font-bold uppercase tracking-[0.1em] text-white/70">
                  GW{week.gameweek}
                </span>
                <div className="relative space-y-6">
                  {rows.map((row, i) => (
                    <div key={i} className="flex flex-wrap justify-center gap-2 sm:gap-4">
                      {row.map((p) => (
                        <PlayerCard key={p.code} p={p} move={moveFor(p, true)} />
                      ))}
                    </div>
                  ))}
                </div>
              </div>

              <Card title="Bench">
                <div className="flex flex-wrap gap-2 sm:gap-4">
                  {week.bench.map((p) => (
                    <PlayerCard key={p.code} p={p} move={moveFor(p, false)} />
                  ))}
                </div>
              </Card>
            </div>

            <PlanLog
              plan={plan}
              changes={changes}
              active={index}
              onSelect={setActiveWeek}
            />
          </div>

          <p className="text-xs text-ink-3">
            15 players · 2 GK / 5 DEF / 5 MID / 3 FWD · max 3 per club · legal formation ·
            one free transfer a gameweek, banked up to 5. Only the XI and captain score, so
            substitutions between the bench and the XI are free — transfers are not, and the
            plan saves them up rather than spending one every week.
          </p>
        </>
      )}

      {loading && !plan && (
        <Card>
          Solving…
          {horizon > 5 && (
            <span className="text-ink-3">
              {" "}
              a {horizon}-gameweek plan takes up to a minute.
            </span>
          )}
        </Card>
      )}
    </div>
  );
}
