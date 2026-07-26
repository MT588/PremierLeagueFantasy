import { FDR_STYLE, RATING_STYLE } from "@/lib/ui";

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-hairline bg-surface p-5 ${className}`}
    >
      {title && (
        <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-ink-3">
          {title}
        </h2>
      )}
      {children}
    </section>
  );
}

export function RatingBadge({ rating }: { rating: string | null }) {
  if (!rating) return <span className="text-ink-3">—</span>;
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs capitalize ${RATING_STYLE[rating] ?? RATING_STYLE.average}`}
    >
      {rating}
    </span>
  );
}

export function FdrChip({
  difficulty,
  label,
  home,
}: {
  difficulty: number | null;
  label: string | null;
  home: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium ${FDR_STYLE[difficulty ?? 3]}`}
      title={`difficulty ${difficulty ?? "?"} · ${home ? "home" : "away"}`}
    >
      {label ?? "?"}
      <span className="opacity-60">{home ? "H" : "A"}</span>
    </span>
  );
}

const STATUS_INFO: Record<string, { label: string; cls: string }> = {
  i: { label: "Injured", cls: "bg-[#d03b3b]/20 text-[#ef8f8f] border-[#d03b3b]/50" },
  d: { label: "Doubtful", cls: "bg-[#ec835a]/15 text-[#f0a888] border-[#ec835a]/40" },
  s: { label: "Suspended", cls: "bg-[#d03b3b]/20 text-[#ef8f8f] border-[#d03b3b]/50" },
  u: { label: "Unavailable", cls: "bg-[#383835] text-[#c3c2b7] border-[#4a4a46]" },
  n: { label: "Unavailable", cls: "bg-[#383835] text-[#c3c2b7] border-[#4a4a46]" },
};

export function StatusBadge({
  status,
  chance,
}: {
  status: string | null;
  chance?: number | null;
}) {
  if (!status || status === "a") return null;
  const info = STATUS_INFO[status] ?? STATUS_INFO.u;
  const label =
    status === "d" && chance != null ? `${info.label} ${chance}%` : info.label;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${info.cls}`}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
        <path d="M4 1h2v5H4zM4 7.5h2V9.5H4z" fill="currentColor" />
      </svg>
      {label}
    </span>
  );
}

export function Sparkline({ points }: { points: number[] }) {
  if (!points.length) return <span className="text-ink-3">—</span>;
  const w = 96;
  const h = 28;
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const step = points.length > 1 ? w / (points.length - 1) : 0;
  const y = (v: number) => h - 3 - ((v - min) / (max - min || 1)) * (h - 6);
  const path = points.map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <svg width={w} height={h} className="block" aria-label={`last ${points.length} gameweeks: ${points.join(", ")} points`}>
      <path d={path} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={(points.length - 1) * step} cy={y(last)} r="2.5" fill="var(--series-1)" />
    </svg>
  );
}
