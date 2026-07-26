export const POSITIONS: Record<number, string> = { 1: "GK", 2: "DEF", 3: "MID", 4: "FWD" };

// FDR 1 (easy) -> 5 (hard). Status-scale colors; the chip always carries the
// opponent label so color never works alone.
export const FDR_STYLE: Record<number, string> = {
  1: "bg-[#0ca30c]/25 text-[#7ee27e] border-[#0ca30c]/40",
  2: "bg-[#0ca30c]/10 text-[#a9d9a9] border-[#0ca30c]/25",
  3: "bg-[#383835] text-[#c3c2b7] border-[#4a4a46]",
  4: "bg-[#ec835a]/15 text-[#f0a888] border-[#ec835a]/40",
  5: "bg-[#d03b3b]/20 text-[#ef8f8f] border-[#d03b3b]/50",
};

export const RATING_STYLE: Record<string, string> = {
  excellent: "bg-[#0ca30c]/15 text-[#7ee27e] border-[#0ca30c]/40",
  good: "bg-[#3987e5]/15 text-[#86b6ef] border-[#3987e5]/40",
  average: "bg-[#383835] text-[#c3c2b7] border-[#4a4a46]",
  poor: "bg-[#d03b3b]/15 text-[#ef8f8f] border-[#d03b3b]/40",
};

export const fmtPrice = (p: number) => `£${p.toFixed(1)}m`;
