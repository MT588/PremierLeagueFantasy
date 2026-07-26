"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, PlayerRow, TeamOut } from "@/lib/api";
import { fmtPrice, POSITIONS } from "@/lib/ui";
import { Card, RatingBadge, Sparkline, StatusBadge } from "@/components/ui";

const SORTS = [
  { key: "predicted_points", label: "Predicted" },
  { key: "form", label: "Form" },
  { key: "xgi90", label: "xGI/90" },
  { key: "total_points_last_season", label: "Last season" },
  { key: "price", label: "Price" },
] as const;

export default function PlayersPage() {
  const [players, setPlayers] = useState<PlayerRow[] | null>(null);
  const [teams, setTeams] = useState<TeamOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState(0);
  const [team, setTeam] = useState(0);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<string>("predicted_points");

  useEffect(() => {
    Promise.all([api.players({ limit: "1000" }), api.teams()])
      .then(([p, t]) => {
        setPlayers(p);
        setTeams(t);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const rows = useMemo(() => {
    if (!players) return [];
    let out = players;
    if (position) out = out.filter((p) => p.position === position);
    if (team) out = out.filter((p) => p.team_code === team);
    if (search) {
      const s = search.toLowerCase();
      out = out.filter(
        (p) => p.web_name.toLowerCase().includes(s) || p.full_name.toLowerCase().includes(s),
      );
    }
    const key = sort as keyof PlayerRow;
    out = [...out].sort((a, b) => {
      const av = a[key] as number | null;
      const bv = b[key] as number | null;
      return (bv ?? -1) - (av ?? -1);
    });
    return out.slice(0, 150);
  }, [players, position, team, search, sort]);

  if (error)
    return <Card>Failed to load players — is the API running? {error}</Card>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Player explorer</h1>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-hairline bg-surface p-0.5 text-sm">
          {[0, 1, 2, 3, 4].map((pos) => (
            <button
              key={pos}
              onClick={() => setPosition(pos)}
              className={`rounded-md px-3 py-1.5 transition-colors ${
                position === pos ? "bg-accent text-white" : "text-ink-2 hover:text-ink"
              }`}
            >
              {pos === 0 ? "All" : POSITIONS[pos]}
            </button>
          ))}
        </div>
        <select
          value={team}
          onChange={(e) => setTeam(Number(e.target.value))}
          className="rounded-lg border border-hairline bg-surface px-3 py-2 text-sm text-ink-2"
        >
          <option value={0}>All teams</option>
          {teams.map((t) => (
            <option key={t.code} value={t.code}>
              {t.name}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="rounded-lg border border-hairline bg-surface px-3 py-2 text-sm text-ink-2"
        >
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              Sort: {s.label}
            </option>
          ))}
        </select>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search players…"
          className="w-48 rounded-lg border border-hairline bg-surface px-3 py-2 text-sm placeholder:text-ink-3"
        />
      </div>

      <div className="overflow-x-auto rounded-xl border border-hairline">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-hairline bg-surface text-left text-xs uppercase tracking-wide text-ink-3">
              <th className="px-4 py-3 font-medium">Player</th>
              <th className="px-3 py-3 font-medium">Pos</th>
              <th className="px-3 py-3 text-right font-medium">Price</th>
              <th className="px-3 py-3 text-right font-medium">Form</th>
              <th className="px-3 py-3 text-right font-medium">xGI/90</th>
              <th className="px-3 py-3 text-right font-medium">Last season</th>
              <th className="px-3 py-3 font-medium">Last 10 GWs</th>
              <th className="px-3 py-3 text-right font-medium">Predicted</th>
              <th className="px-4 py-3 font-medium">Rating</th>
            </tr>
          </thead>
          <tbody>
            {players === null ? (
              <tr>
                <td colSpan={9} className="px-4 py-10 text-center text-ink-3">
                  Loading…
                </td>
              </tr>
            ) : (
              rows.map((p) => (
                <tr key={p.code} className="border-b border-hairline/50 last:border-0 hover:bg-surface/60">
                  <td className="px-4 py-2.5">
                    <Link href={`/players/${p.code}`} className="hover:text-accent">
                      {p.web_name}
                    </Link>
                    <span className="ml-1.5 text-xs text-ink-3">{p.team_short}</span>
                    <span className="ml-1.5">
                      <StatusBadge status={p.status} chance={p.chance_of_playing} />
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-ink-2">{POSITIONS[p.position]}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-2">{fmtPrice(p.price)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-2">{p.form ?? "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-2">{p.xgi90 ?? "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-2">
                    {p.total_points_last_season ?? "—"}
                  </td>
                  <td className="px-3 py-2.5">
                    <Sparkline points={p.recent_points} />
                  </td>
                  <td className="px-3 py-2.5 text-right font-medium tabular-nums">
                    {p.predicted_points?.toFixed(2) ?? "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <RatingBadge rating={p.rating} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">
        Showing {rows.length} players · form = avg points over the last 5 appearances ·
        predicted = model points for the next gameweek.
      </p>
    </div>
  );
}
