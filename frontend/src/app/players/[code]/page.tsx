import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { fmtPrice, POSITIONS } from "@/lib/ui";
import { Card, FdrChip, RatingBadge } from "@/components/ui";
import PointsChart from "@/components/PointsChart";

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
            {player.status && player.status !== "a" && (
              <span className="ml-2 rounded-md bg-[#d03b3b]/20 px-2 py-0.5 text-xs text-[#ef8f8f]">
                flagged: {player.status}
              </span>
            )}
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
    </div>
  );
}
