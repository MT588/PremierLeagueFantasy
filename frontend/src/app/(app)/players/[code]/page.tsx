import { notFound } from "next/navigation";
import { PredictionDrivers } from "@/lib/api";
import { api } from "@/lib/api.server";
import { fmtPrice, POSITIONS } from "@/lib/ui";
import { Card, FdrChip, RatingBadge, StatusBadge } from "@/components/ui";
import PointsChart from "@/components/PointsChart";

const COMPONENT_LABELS: Record<string, string> = {
  appearance: "Turning up",
  goals: "Goal threat",
  assists: "Creativity",
  clean_sheet: "Clean sheet",
  saves: "Saves",
  defensive: "Defensive actions",
  bonus: "Bonus",
  cards: "Cards",
};

/** A bar per contribution, shared by both driver shapes. */
function ContributionBar({
  label,
  value,
  maxAbs,
}: {
  label: string;
  value: number;
  maxAbs: number;
}) {
  const up = value > 0;
  return (
    <li className="text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-ink-2">{label}</span>
        <span
          className={`shrink-0 tabular-nums ${up ? "text-[#1E5C36]" : "text-[#8A2E20]"}`}
        >
          {up ? "+" : ""}
          {value.toFixed(2)}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-page">
        <div
          className={`h-full rounded-full ${up ? "bg-[#3E8E5A]" : "bg-[#C0392B]"}`}
          style={{ width: `${(Math.abs(value) / maxAbs) * 100}%` }}
        />
      </div>
    </li>
  );
}

/** v3 explains a prediction as the sum it actually is — points priced per part
 *  of the game — where v2 could only offer SHAP attributions over 76 features.
 *  Both shapes are rendered because predictions written by either model version
 *  can still be in the table. */
function DriversPanel({ drivers }: { drivers: PredictionDrivers }) {
  const components = drivers.components ?? [];
  const isV3 = components.length > 0;
  const rows = isV3
    ? components.map((c) => ({
        key: c.name,
        label: COMPONENT_LABELS[c.name] ?? c.name,
        value: c.points,
      }))
    : (drivers.top ?? []).map((d) => ({
        key: d.feature,
        label: d.label,
        value: d.contribution,
      }));

  if (rows.length === 0) return null;
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.value)), 0.01);

  return (
    <Card title="What drives this prediction">
      {drivers.gated && (
        <p className="mb-3 rounded-md bg-[#F2E4E1] px-3 py-2 text-xs text-[#8A2E20]">
          Currently unavailable — prediction set to zero regardless of the inputs below.
        </p>
      )}
      <div className="mb-3 flex gap-4 text-xs text-ink-2">
        <span>
          Start chance:{" "}
          <span className="font-semibold tabular-nums text-ink">
            {Math.round(drivers.p_start * 100)}%
          </span>
        </span>
        <span>
          If starting:{" "}
          <span className="font-semibold tabular-nums text-ink">
            {drivers.expected_if_start.toFixed(1)} pts
          </span>
        </span>
      </div>
      <ul className="space-y-2">
        {rows.map((r) => (
          <ContributionBar key={r.key} label={r.label} value={r.value} maxAbs={maxAbs} />
        ))}
      </ul>
      <p className="mt-3 text-[11px] text-ink-3">
        {isV3
          ? "Where the points come from, priced by the official scoring rules."
          : "Contribution of each input to the points-if-starting estimate (model SHAP values)."}
      </p>
    </Card>
  );
}

export const dynamic = "force-dynamic";

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  let player;
  try {
    player = await api.player(Number(code));
  } catch {
    notFound();
  }

  const seasonTotals = new Map<string, { pts: number; mins: number }>();
  for (const h of player.history) {
    const t = seasonTotals.get(h.season) ?? { pts: 0, mins: 0 };
    t.pts += h.total_points;
    t.mins += h.minutes;
    seasonTotals.set(h.season, t);
  }
  const totals = [...seasonTotals.entries()].sort().reverse();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{player.full_name}</h1>
          <p className="mt-1 text-sm text-ink-2">
            {POSITIONS[player.position] ?? "—"} · {player.team_short ?? "not in current pool"} ·{" "}
            {fmtPrice(player.price)}
            <span className="ml-2">
              <StatusBadge status={player.status} chance={player.chance_of_playing} />
            </span>
          </p>
        </div>
        <div className="flex gap-6 text-right">
          {totals.slice(0, 3).map(([season, t]) => (
            <div key={season}>
              <div className="text-xs text-ink-3">{season}</div>
              <div className="text-lg font-semibold tabular-nums">{t.pts} pts</div>
              <div className="text-xs text-ink-3">{t.mins} min</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Points per gameweek" className="lg:col-span-2">
          <PointsChart history={player.history} />
        </Card>

        <div className="space-y-4">
          <Card title="Predicted next gameweeks">
            {player.predictions.length === 0 ? (
              <p className="text-sm text-ink-3">No predictions stored.</p>
            ) : (
              <ul className="space-y-2">
                {player.predictions.map((p) => (
                  <li key={p.gameweek} className="flex items-center justify-between text-sm">
                    <span className="text-ink-2">GW{p.gameweek}</span>
                    <span className="flex items-center gap-2">
                      <span className="font-medium tabular-nums">
                        {p.predicted_points.toFixed(2)}
                      </span>
                      <RatingBadge rating={p.rating} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Upcoming fixtures">
            {player.upcoming.length === 0 ? (
              <p className="text-sm text-ink-3">No fixtures scheduled.</p>
            ) : (
              <ul className="space-y-2">
                {player.upcoming.map((f, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="text-ink-2">GW{f.gameweek ?? "?"}</span>
                    <FdrChip
                      difficulty={f.difficulty}
                      label={f.opponent_short}
                      home={f.was_home}
                    />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {player.predictions[0]?.drivers && (
        <div className="grid gap-4 lg:grid-cols-3">
          <DriversPanel drivers={player.predictions[0].drivers} />
        </div>
      )}
    </div>
  );
}
