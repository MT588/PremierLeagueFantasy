"use client";

import { StatsPage } from "@/components/StatsPage";
import { InfoBox } from "@/components/ui";
import {
  blankCol,
  epCol,
  haulCol,
  isAvailable,
  nameCol,
  oppCol,
  ownCol,
  p10Col,
  p90Col,
  posCol,
  ppmCol,
  priceCol,
  pStartCol,
  rankCol,
  returnCol,
  teamCol,
} from "@/components/columns";
import { Column } from "@/components/DataTable";
import { PlayerStats } from "@/lib/api";
import { RatingBadge } from "@/components/ui";

const columns: Column<PlayerStats>[] = [
  rankCol,
  nameCol,
  teamCol,
  posCol,
  priceCol,
  epCol,
  haulCol,
  p90Col,
  { key: "rating", label: "Rating", render: (p) => <RatingBadge rating={p.rating} /> },
  pStartCol,
  returnCol,
  blankCol,
  p10Col,
  ppmCol,
  oppCol,
  ownCol,
];

export default function CaptaincyPage() {
  return (
    <StatsPage
      n={2}
      title="Captaincy & expected points"
      columns={columns}
      initialSort={{ key: "predicted_points" }}
      limit={50}
      prefilter={isAvailable}
      intro={
        <InfoBox>
          <b>Predicted</b> is this app&apos;s own model. It estimates the chance of
          starting, then prices each part of the game separately — goals, assists,
          clean sheets, saves, defensive contributions, bonus and cards — and simulates
          the week thousands of times to get a full range of outcomes rather than a
          single number. It is trained on five seasons of gameweek history plus
          Understat shot data, set-piece duties and opponent strength.
          <br />
          <br />
          <b>Haul %</b> is how often that simulation returns 10 or more points, and{" "}
          <b>Ceiling</b> is the score a good week reaches (the top tenth of outcomes).
          Those are the captaincy numbers: two players on the same predicted score are
          not the same pick if one is a steady six and the other is a two-or-fifteen.{" "}
          <b>Start %</b> is the rotation risk on its own — a high predicted score off a
          low start probability is not a safe armband. Players ruled out of the next
          match are filtered out.
        </InfoBox>
      }
      footer={
        <p className="text-xs text-ink-2">
          The table ranks on predicted points. Weighting the ranking toward Haul %
          instead was tested against four seasons of held-out gameweeks and did not
          improve either the points or the haul rate of the resulting shortlist, so
          the upside columns are shown and sortable rather than blended into the
          ranking. Ownership is overall selected-by %, which is <b>not</b> the same as
          captaincy ownership — plenty of managers own a player without giving him the
          armband.
        </p>
      }
    />
  );
}
