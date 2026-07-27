import Link from "next/link";
import { PlayerStats } from "@/lib/api";
import { fmt, fmtPrice } from "@/lib/ui";
import { Column } from "@/components/DataTable";
import { EpBadge, PosBadge, RankPill, StartsCell, StatusBadge } from "@/components/ui";

type Col = Column<PlayerStats>;

/** Rank reflects the current sort, so it renumbers when you re-sort. */
export const rankCol: Col = {
  key: "_rank",
  label: "#",
  sortable: false,
  render: (_p, i) => <RankPill n={i + 1} />,
};

export const nameCol: Col = {
  key: "web_name",
  label: "Player",
  render: (p) => (
    <>
      <Link
        href={`/players/${p.code}`}
        // Prefetching 404s in production — see Sidebar.tsx. Worst offender:
        // up to 300 rows on screen, each retrying every 10 seconds.
        prefetch={false}
        className="hover:text-pitch hover:underline"
      >
        {p.web_name}
      </Link>
      {p.chance_of_playing === 0 && (
        <span className="ml-1.5 text-[11px] font-bold text-[#C0392B]">OUT</span>
      )}
      <span className="ml-1.5">
        <StatusBadge status={p.status} chance={p.chance_of_playing} />
      </span>
    </>
  ),
};

export const teamCol: Col = {
  key: "team_short",
  label: "Team",
  optional: true,
  render: (p) => p.team_short ?? "—",
};

export const posCol: Col = {
  key: "position",
  label: "Pos",
  render: (p) => <PosBadge position={p.position} />,
};

export const priceCol: Col = {
  key: "price",
  label: "£m",
  numeric: true,
  render: (p) => fmtPrice(p.price),
};

export const epCol: Col = {
  key: "predicted_points",
  label: "Predicted",
  numeric: true,
  render: (p) => <EpBadge value={p.predicted_points} />,
};

export const ppmCol: Col = {
  key: "points_per_million",
  label: "Pts/£m",
  numeric: true,
  render: (p) => fmt(p.points_per_million, 1),
};

export const startsCol: Col = {
  key: "starts_share",
  label: "Started",
  numeric: true,
  render: (p) => (
    <StartsCell
      share={p.starts_share}
      starts={p.starts}
      games={p.starts_share && p.starts ? Math.round(p.starts / p.starts_share) : null}
    />
  ),
};

export const oppCol: Col = {
  key: "next_opponent",
  label: "Next",
  optional: true,
  render: (p) => p.next_opponent ?? "—",
};

export const fdrCol: Col = {
  key: "next_fdr",
  label: "FDR",
  numeric: true,
  optional: true,
  render: (p) => p.next_fdr ?? "—",
};

export const ownCol: Col = {
  key: "selected_by_percent",
  label: "Sel %",
  numeric: true,
  optional: true,
  render: (p) => (p.selected_by_percent === null ? "—" : `${p.selected_by_percent.toFixed(1)}%`),
};

export const pStartCol: Col = {
  key: "p_start",
  label: "Start %",
  numeric: true,
  optional: true,
  render: (p) => (p.p_start === null ? "—" : `${Math.round(p.p_start * 100)}%`),
};

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

/** v3 distributional columns. The model predicts a distribution per player, not
 *  just a mean, and these are the parts of it a manager actually decides on:
 *  two players on the same expected points are not interchangeable if one is a
 *  steady six and the other is a two-or-fifteen. Null on rows a pre-v3 model
 *  wrote, so every one of these renders an em dash rather than a zero. */
export const haulCol: Col = {
  key: "p_haul",
  label: "Haul %",
  numeric: true,
  render: (p) => pct(p.p_haul),
};

export const returnCol: Col = {
  key: "p_return",
  label: "Return %",
  numeric: true,
  optional: true,
  render: (p) => pct(p.p_return),
};

export const blankCol: Col = {
  key: "p_blank",
  label: "Blank %",
  numeric: true,
  optional: true,
  render: (p) => pct(p.p_blank),
};

/** The ceiling: a tenth of weeks come in at or above this. */
export const p90Col: Col = {
  key: "p90",
  label: "Ceiling",
  numeric: true,
  render: (p) => fmt(p.p90, 0),
};

/** The floor, and the reason a high mean is not automatically a safe pick. */
export const p10Col: Col = {
  key: "p10",
  label: "Floor",
  numeric: true,
  optional: true,
  render: (p) => fmt(p.p10, 0),
};

/** Players the model has ruled out of the next match are noise in every
 *  ranking view, so each table drops them before filtering. */
export const isAvailable = (p: PlayerStats) => p.chance_of_playing !== 0;
