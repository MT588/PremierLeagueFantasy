"use client";

import { StatsPage } from "@/components/StatsPage";
import { Note, Sparkline } from "@/components/ui";
import {
  epCol,
  nameCol,
  oppCol,
  ownCol,
  posCol,
  ppmCol,
  priceCol,
  startsCol,
  teamCol,
} from "@/components/columns";
import { Column } from "@/components/DataTable";
import { PlayerStats } from "@/lib/api";
import { fmt } from "@/lib/ui";

const columns: Column<PlayerStats>[] = [
  nameCol,
  teamCol,
  posCol,
  priceCol,
  epCol,
  { key: "total_points", label: "Points", numeric: true, render: (p) => p.total_points },
  { key: "ppg", label: "PPG", numeric: true, render: (p) => fmt(p.ppg, 1) },
  ppmCol,
  startsCol,
  {
    key: "xgi90_season",
    label: "xGI/90",
    numeric: true,
    optional: true,
    render: (p) => fmt(p.xgi90_season, 2),
  },
  {
    key: "dc90_season",
    label: "DefCon/90",
    numeric: true,
    optional: true,
    render: (p) => fmt(p.dc90_season, 1),
  },
  {
    key: "form_points",
    label: "Form",
    numeric: true,
    optional: true,
    render: (p) =>
      p.form_points === null ? (
        "—"
      ) : (
        <>
          {p.form_points}
          <span className="ml-1 text-[10.5px] text-ink-2">{p.form_minutes}′</span>
        </>
      ),
  },
  ownCol,
  oppCol,
  {
    key: "_spark",
    label: "Last 10 GWs",
    sortable: false,
    optional: true,
    render: (p) => <Sparkline points={p.recent_points} />,
  },
];

export default function PlayersPage() {
  return (
    <StatsPage
      n={1}
      title="All players"
      columns={columns}
      initialSort={{ key: "predicted_points" }}
      limit={300}
      intro={
        <Note>
          Every player in the current pool. <b>Predicted</b>{" "}
          is the model&apos;s points for
          the next gameweek; <b>Points</b>, <b>PPG</b> and <b>Pts/£m</b> come from the most
          recent season with played matches, while price, ownership and the next opponent
          are current. <b>Form</b> is points over the last 5 appearances, with minutes
          played beside it. On a narrow screen some columns are hidden — turn the phone
          sideways or swipe the table across to see them all.
        </Note>
      }
      footer={
        <p className="text-xs text-ink-2">
          Showing at most 300 rows. Narrow the list with the filters above, or click any
          player for their gameweek history and the drivers behind their prediction.
        </p>
      }
    />
  );
}
