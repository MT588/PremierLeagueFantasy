import Link from "next/link";
import { PlayerRow } from "@/lib/api";
import { api } from "@/lib/api.server";
import { fmtPrice, POSITIONS } from "@/lib/ui";
import { Card, RatingBadge, SectionTitle, StatusBadge } from "@/components/ui";

export const dynamic = "force-dynamic";

function TopBarList({ players }: { players: PlayerRow[] }) {
  const max = Math.max(...players.map((p) => p.predicted_points ?? 0), 0.1);
  return (
    <ol className="space-y-2">
      {players.map((p, i) => (
        <li key={p.code}>
          <Link
            href={`/players/${p.code}`}
            // Prefetching 404s in production — see Sidebar.tsx.
            prefetch={false}
            className="group grid grid-cols-[1.5rem_11rem_1fr_3rem] items-center gap-3"
          >
            <span className="text-right text-xs tabular-nums text-ink-3">{i + 1}</span>
            <span className="truncate text-sm group-hover:text-accent">
              {p.web_name}
              <span className="ml-1.5 text-xs text-ink-3">
                {p.team_short} · {POSITIONS[p.position]}
              </span>
            </span>
            <span className="h-4 overflow-hidden rounded-r-[4px]">
              <span
                className="block h-full rounded-r-[4px] bg-accent transition-opacity group-hover:opacity-80"
                style={{ width: `${((p.predicted_points ?? 0) / max) * 100}%` }}
              />
            </span>
            <span className="text-right text-sm tabular-nums text-ink-2">
              {p.predicted_points?.toFixed(1)}
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

export default async function Dashboard() {
  const [meta, players] = await Promise.all([api.meta(), api.players({ limit: "400" })]);
  const top10 = players.slice(0, 10);
  const byPosition = ([2, 3, 4, 1] as const).map((pos) => ({
    pos,
    rows: players.filter((p) => p.position === pos).slice(0, 10),
  }));

  return (
    <div className="space-y-6">
      <SectionTitle n={1}>Dashboard</SectionTitle>
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <div className="text-xs uppercase tracking-wide text-ink-3">Season</div>
          <div className="mt-1 text-2xl font-semibold">{meta.season}</div>
          <div className="mt-1 text-sm text-ink-2">next gameweek: GW{meta.next_gameweek}</div>
        </Card>
        <Card>
          <div className="text-xs uppercase tracking-wide text-ink-3">Player pool</div>
          <div className="mt-1 text-2xl font-semibold">{meta.players_in_pool}</div>
          <div className="mt-1 text-sm text-ink-2">{meta.predictions} predictions stored</div>
        </Card>
        <Card>
          <div className="text-xs uppercase tracking-wide text-ink-3">Model</div>
          <div className="mt-1 text-2xl font-semibold">{meta.model_version}</div>
          <div className="mt-1 text-sm text-ink-2">
            {/* Prefetching 404s in production — see Sidebar.tsx. */}
            <Link href="/team" prefetch={false} className="text-accent hover:underline">
              view optimal team →
            </Link>
          </div>
        </Card>
      </div>

      <Card title={`Top 10 predicted points — GW${meta.next_gameweek}`}>
        <TopBarList players={top10} />
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {byPosition.map(({ pos, rows }) => (
          <Card key={pos} title={`Top ${POSITIONS[pos]}`}>
            <ul className="space-y-2.5">
              {rows.map((p) => (
                <li key={p.code} className="flex items-center justify-between gap-2 text-sm">
                  <Link
                    href={`/players/${p.code}`}
                    prefetch={false}
                    className="truncate hover:text-accent"
                  >
                    {p.web_name}
                    <span className="ml-1.5 text-xs text-ink-3">{p.team_short}</span>
                    <span className="ml-1.5 align-middle">
                      <StatusBadge status={p.status} chance={p.chance_of_playing} />
                    </span>
                  </Link>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-ink-3">{fmtPrice(p.price)}</span>
                    <RatingBadge rating={p.rating} />
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  );
}
