import { epClass, FDR_STYLE, POSITION_STYLE, POSITIONS, RATING_STYLE } from "@/lib/ui";

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
  i: { label: "Injured", cls: "bg-[#F2E4E1] text-[#8A2E20] border-[#C0392B]/40" },
  d: { label: "Doubtful", cls: "bg-[#FBF0DC] text-[#6B5417] border-[#E08B3D]/45" },
  s: { label: "Suspended", cls: "bg-[#F2E4E1] text-[#8A2E20] border-[#C0392B]/40" },
  u: { label: "Unavailable", cls: "bg-[#EDEAE0] text-[#6B6B63] border-[#E4E0D4]" },
  n: { label: "Unavailable", cls: "bg-[#EDEAE0] text-[#6B6B63] border-[#E4E0D4]" },
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

export function PosBadge({ position }: { position: number }) {
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[10.5px] font-bold ${POSITION_STYLE[position] ?? ""}`}
    >
      {POSITIONS[position] ?? "?"}
    </span>
  );
}

export function EpBadge({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <span className="text-ink-3">—</span>;
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-bold ${epClass(value)}`}>
      {value.toFixed(1)}
    </span>
  );
}

/** Share of the club's matches this player started. A high per-90 rate over two
 *  appearances says nothing, so every rate column is read next to this. */
export function StartsCell({
  share,
  starts,
  games,
}: {
  share: number | null;
  starts: number | null;
  games: number | null;
}) {
  if (share === null || share === undefined) return <span className="text-ink-3">—</span>;
  const cls = share >= 0.7 ? "hi" : share >= 0.4 ? "mid" : "lo";
  const style =
    cls === "hi"
      ? "bg-[#DCEEE2] text-[#1E5C36]"
      : cls === "mid"
        ? "bg-[#FBF0DC] text-[#6B5417]"
        : "bg-[#F2E4E1] text-[#8A2E20]";
  return (
    <>
      <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-bold ${style}`}>
        {Math.round(share * 100)}%
      </span>
      {starts !== null && games ? (
        <span className="ml-1 text-[10.5px] text-ink-2">
          {starts}/{games}
        </span>
      ) : null}
    </>
  );
}

/** Net transfers as a price-movement signal. FPL never publishes the actual
 *  threshold, so this is directional only. */
export function TrendCell({ net }: { net: number }) {
  if (net > 1000)
    return <span className="font-bold text-[#3E8E5A]">↑ may rise</span>;
  if (net < -1000)
    return <span className="font-bold text-[#C0392B]">↓ may fall</span>;
  return <span className="text-ink-2">stable</span>;
}

export function RankPill({ n }: { n: number }) {
  return (
    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-gold text-[11px] font-bold text-ink">
      {n}
    </span>
  );
}

export function SectionTitle({
  n,
  children,
  aside,
}: {
  n?: number;
  children: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <h1 className="mb-3.5 flex items-center gap-2 font-display text-[13px] font-bold uppercase tracking-[0.1em] text-pitch">
      {n !== undefined && (
        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-pitch text-[11px] text-white">
          {n}
        </span>
      )}
      {children}
      {aside && (
        <span className="font-sans text-xs font-normal normal-case tracking-normal text-ink-2">
          {aside}
        </span>
      )}
    </h1>
  );
}

export function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-3.5 text-[12.5px] leading-relaxed text-ink-2">{children}</p>
  );
}

export function WarnBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-[#E8C547] bg-[#FBF0DC] px-4 py-3 text-[12.5px] leading-relaxed text-[#6B5417]">
      {children}
    </div>
  );
}

export function InfoBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-[#CFE0D6] bg-[#EEF4F0] px-3.5 py-2.5 text-[12.5px] leading-relaxed text-ink-2">
      {children}
    </div>
  );
}

/** Horizontal bar used by the team-strength view. Each metric is scaled
 *  against its own maximum: FPL rates overall strength 1-5 but attack and
 *  defence in the 1000-1400 range, so a shared scale would be meaningless. */
export function StrengthBar({
  label,
  value,
  max,
  variant,
}: {
  label: string;
  value: number;
  max: number;
  variant: "att" | "def";
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div>
      <div className="mb-1 text-[10.5px] uppercase tracking-[0.06em] text-ink-2">
        {label}
      </div>
      <div className="h-2.5 overflow-hidden rounded bg-grid">
        <div
          className={`h-full rounded ${
            variant === "att"
              ? "bg-gradient-to-r from-[#8FBF6B] to-[#14543F]"
              : "bg-gradient-to-r from-[#C9A227] to-[#0B3D2E]"
          }`}
          style={{ width: `${pct.toFixed(0)}%` }}
        />
      </div>
    </div>
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
