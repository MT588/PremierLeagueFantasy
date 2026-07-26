"use client";

import { StatsPage } from "@/components/StatsPage";
import { InfoBox } from "@/components/ui";
import {
  epCol,
  isAvailable,
  nameCol,
  oppCol,
  ownCol,
  posCol,
  ppmCol,
  priceCol,
  pStartCol,
  rankCol,
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
  { key: "rating", label: "Rating", render: (p) => <RatingBadge rating={p.rating} /> },
  pStartCol,
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
          <b>Predicted</b>{" "}
          is this app&apos;s own model: a two-stage LightGBM that first
          estimates the chance of starting, then the points to expect if the player does.
          It is trained on five seasons of gameweek history plus Understat shot data,
          set-piece duties and opponent strength. <b>Start %</b> is the first stage on its
          own — a high predicted score off a low start probability is a rotation risk, not
          a safe captain. Players ruled out of the next match are filtered out.
        </InfoBox>
      }
      footer={
        <p className="text-xs text-ink-2">
          Ownership is overall selected-by %, which is <b>not</b> the same as captaincy
          ownership — plenty of managers own a player without giving him the armband.
        </p>
      }
    />
  );
}
