"use client";

import { StatsPage } from "@/components/StatsPage";
import { TrendCell, WarnBox } from "@/components/ui";
import { nameCol, ownCol, posCol, priceCol, teamCol } from "@/components/columns";
import { Column } from "@/components/DataTable";
import { PlayerStats } from "@/lib/api";

const int = (
  key: keyof PlayerStats & string,
  label: string,
): Column<PlayerStats> => ({
  key,
  label,
  numeric: true,
  render: (p) => {
    const v = p[key] as number | null;
    return v === null ? "—" : v.toLocaleString();
  },
});

const columns: Column<PlayerStats>[] = [
  nameCol,
  teamCol,
  posCol,
  priceCol,
  int("transfers_in_event", "Transfers in"),
  int("transfers_out_event", "Transfers out"),
  int("net_transfers", "Net"),
  {
    key: "_dir",
    label: "Direction",
    sortable: false,
    render: (p) => <TrendCell net={p.net_transfers} />,
  },
  ownCol,
];

export default function PricesPage() {
  return (
    <StatsPage
      n={5}
      title="Price movement — net transfers"
      columns={columns}
      initialSort={{ key: "net_transfers" }}
      limit={50}
      intro={
        <WarnBox>
          Net transfers within the current gameweek are the momentum indicator behind price
          changes. FPL never publishes the actual threshold, so treat the direction column
          as suggestive, not a forecast — watch a player over several days before acting.
          <br />
          <br />
          Two things flatten this table. Before the first deadline most managers have not
          picked a squad yet, so the counts sit at zero for everyone. And these are live
          snapshot values: they are only as fresh as the last{" "}
          <code className="rounded bg-[#F0EEE6] px-1">--live</code> pipeline run, which is
          manual. Re-run the pipeline to refresh.
        </WarnBox>
      }
    />
  );
}
