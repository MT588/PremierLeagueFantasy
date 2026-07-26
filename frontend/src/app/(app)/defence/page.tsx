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
  dec: number,
  optional = false,
): Column<PlayerStats> => ({
  key,
  label,
  numeric: true,
  optional,
  render: (p) => fmt(p[key] as number | null, dec),
});

const columns: Column<PlayerStats>[] = [
  nameCol,
  teamCol,
  posCol,
  startsCol,
  num("dc90_form", "DefCon form", 1),
  num("dc90_season", "DefCon season", 1),
  num("team_xgc90_form", "Team xGC form", 2, true),
  num("team_xgc90_season", "Team xGC season", 2, true),
  oppCol,
  epCol,
];

export default function DefencePage() {
  return (
    <StatsPage
      n={4}
      title="Defence — clean sheets and DefCon"
      columns={columns}
      initialSort={{ key: "dc90_season" }}
      limit={100}
      prefilter={isAvailable}
      intro={
        <Note>
          <b>DefCon</b>{" "}
          is defensive contributions per 90 minutes. The threshold for a
          point is 10 actions for defenders and 12 for midfielders and forwards. FPL only
          began recording it in 2025-26, so there is no earlier history to fall back on.
          <br />
          <br />
          <b>Team xGC</b>{" "}
          is the club&apos;s expected goals conceded per match, derived
          from its most-used keeper — he is on the pitch for the full 90, so his xGC per 90
          is the team&apos;s xGC per match. It is a team value, so it reads the same for
          every player at that club. Lower is better: it is the clean-sheet signal.
          <br />
          <br />
          <b>Started</b>{" "}
          shows how often the player was in the XI, against the number of
          matches his club played. Weigh every rate column against it — fourteen actions
          per 90 across two appearances is noise. Rates are left blank below a minimum
          sample (90 minutes for form, 270 for the season), and blanks always sort last.
        </Note>
      }
    />
  );
}
