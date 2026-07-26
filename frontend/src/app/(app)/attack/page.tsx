"use client";

import { StatsPage } from "@/components/StatsPage";
import { Note } from "@/components/ui";
import {
  epCol,
  isAvailable,
  nameCol,
  oppCol,
  posCol,
  startsCol,
  teamCol,
} from "@/components/columns";
import { Column } from "@/components/DataTable";
import { PlayerStats } from "@/lib/api";
import { fmt } from "@/lib/ui";

const num = (
  key: keyof PlayerStats & string,
  label: string,
  opts: { optional?: boolean; bold?: boolean } = {},
): Column<PlayerStats> => ({
  key,
  label,
  numeric: true,
  optional: opts.optional,
  render: (p) => {
    const v = p[key] as number | null;
    const text = fmt(v, 2);
    return opts.bold ? <b>{text}</b> : text;
  },
});

const columns: Column<PlayerStats>[] = [
  nameCol,
  teamCol,
  posCol,
  startsCol,
  num("xg90_form", "xG form", { optional: true }),
  num("xa90_form", "xA form", { optional: true }),
  num("xgi90_form", "xG+A form", { bold: true }),
  num("xg90_season", "xG season", { optional: true }),
  num("xa90_season", "xA season", { optional: true }),
  num("xgi90_season", "xG+A season", { bold: true }),
  oppCol,
  epCol,
];

export default function AttackPage() {
  return (
    <StatsPage
      n={3}
      title="Attack — xG and xA"
      columns={columns}
      initialSort={{ key: "xgi90_season" }}
      limit={100}
      prefilter={isAvailable}
      intro={
        <Note>
          All figures are per 90 minutes. The <b>xG+A</b> columns are goal plus assist
          expectation combined, and are bolded because that is usually the number you
          compare on. <b>Form</b> averages the last 5 appearances; <b>season</b> covers the
          whole of the most recent season with played matches. Read both next to{" "}
          <b>Started</b>: a big per-90 rate over two appearances means nothing. Rates are
          left blank below a minimum sample — 90 minutes for form, 270 for the season — and
          blanks always sort last. To tighten it further, add a column filter on Started
          with a minimum.
        </Note>
      }
    />
  );
}
