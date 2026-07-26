export const POSITIONS: Record<number, string> = { 1: "GK", 2: "DEF", 3: "MID", 4: "FWD" };

// FDR 1 (easy) -> 5 (hard). The chip always carries the opponent label so
// colour never works alone.
export const FDR_STYLE: Record<number, string> = {
  1: "bg-[#3E8E5A]/20 text-[#215C38] border-[#3E8E5A]/45",
  2: "bg-[#8FBF6B]/25 text-[#4A6B33] border-[#8FBF6B]/50",
  3: "bg-[#E8C547]/25 text-[#6B5417] border-[#E8C547]/55",
  4: "bg-[#E08B3D]/22 text-[#8A5017] border-[#E08B3D]/50",
  5: "bg-[#C0392B]/18 text-[#8A2E20] border-[#C0392B]/45",
};

export const RATING_STYLE: Record<string, string> = {
  excellent: "bg-[#DCEEE2] text-[#1E5C36] border-[#3E8E5A]/40",
  good: "bg-[#E7F0E9] text-[#2E6B4F] border-[#2E6B4F]/25",
  average: "bg-[#FBF0DC] text-[#6B5417] border-[#E8C547]/50",
  poor: "bg-[#F2E4E1] text-[#8A2E20] border-[#C0392B]/35",
};

// Expected-points scale, mirroring the rating bands for rows where the model
// gives a number but no rating label.
export const EP_STYLE = {
  hi: "bg-[#DCEEE2] text-[#1E5C36]",
  mid: "bg-[#FBF0DC] text-[#6B5417]",
  lo: "bg-[#F2E4E1] text-[#8A2E20]",
} as const;

export const epClass = (v: number) => (v >= 5 ? EP_STYLE.hi : v >= 3 ? EP_STYLE.mid : EP_STYLE.lo);

export const POSITION_STYLE: Record<number, string> = {
  1: "bg-[#5B6B73] text-white",
  2: "bg-[#2E6B4F] text-white",
  3: "bg-[#C9A227] text-[#1C1C1C]",
  4: "bg-[#B0402E] text-white",
};

export const fmtPrice = (p: number) => `£${p.toFixed(1)}m`;

export const fmt = (v: number | null | undefined, dec = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(dec);

export const fmtPct = (v: number | null | undefined, dec = 0) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(dec)}%`;
