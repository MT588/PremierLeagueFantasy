"use client";

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { GameweekPoint } from "@/lib/api";

export default function PointsChart({ history }: { history: GameweekPoint[] }) {
  const seasons = useMemo(
    () => [...new Set(history.map((h) => h.season))].sort().reverse(),
    [history],
  );
  const [season, setSeason] = useState(seasons[0]);
  const data = history.filter((h) => h.season === season);

  if (!history.length) return <p className="text-sm text-ink-3">No gameweek history yet.</p>;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1">
        {seasons.map((s) => (
          <button
            key={s}
            onClick={() => setSeason(s)}
            className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
              season === s ? "bg-accent text-white" : "bg-page text-ink-2 hover:text-ink"
            }`}
          >
            {s}
          </button>
        ))}
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="gameweek"
              stroke="var(--ink-3)"
              tickLine={false}
              axisLine={{ stroke: "var(--grid)" }}
              fontSize={11}
              interval={4}
            />
            <YAxis
              stroke="var(--ink-3)"
              tickLine={false}
              axisLine={false}
              fontSize={11}
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.05)" }}
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--hairline)",
                borderRadius: "8px",
                fontSize: "12px",
                color: "var(--ink)",
              }}
              labelFormatter={(gw) => `Gameweek ${gw}`}
              formatter={(value, name) => [
                value,
                name === "total_points" ? "points" : String(name),
              ]}
            />
            <Bar
              dataKey="total_points"
              fill="var(--series-1)"
              radius={[4, 4, 0, 0]}
              maxBarSize={14}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
