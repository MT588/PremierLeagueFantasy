import Link from "next/link";
import { Suspense } from "react";
import { MetaStrip } from "@/components/MetaStrip";
import { Sidebar } from "@/components/Sidebar";

/** Chrome for the signed-in dashboard. */
export default function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 bg-pitch px-5 py-4 text-white sm:px-7">
        <Link href="/">
          <div className="font-display text-[11px] font-bold uppercase tracking-[0.12em] text-gold">
            Fantasy Premier League
          </div>
          <h1 className="font-display text-[22px] font-black tracking-tight">
            Fixture &amp; Form Dashboard
          </h1>
        </Link>
        <Suspense fallback={null}>
          <MetaStrip />
        </Suspense>
      </header>

      <div className="mx-auto flex w-full max-w-[1400px] flex-1 flex-col items-stretch lg:flex-row lg:items-start">
        <Sidebar />
        <main className="min-w-0 flex-1 px-3 pb-14 lg:px-6 lg:py-6">{children}</main>
      </div>

      <footer className="px-5 py-5 text-[11.5px] leading-relaxed text-ink-2 sm:px-7">
        Source: official FPL API, vaastav/Fantasy-Premier-League, Understat, ClubElo.
        Form = the last 5 appearances; season figures come from the most recent season
        with played matches. Predicted points are model estimates, not guarantees.
      </footer>
    </>
  );
}
