"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { getSupabaseBrowser } from "@/lib/supabase/client";

/** `prefetch: false` marks a force-dynamic route: it has no static shell, so
 *  Next answers the prefetch with a 404 and retries it every 10 seconds for as
 *  long as the sidebar is on screen — which is always. */
const GROUPS: {
  label: string;
  items: { href: string; label: string; prefetch?: false }[];
}[] = [
  {
    label: "Overview",
    items: [{ href: "/", label: "Dashboard", prefetch: false }],
  },
  {
    label: "Analysis",
    items: [
      { href: "/teams", label: "Team strength" },
      { href: "/captaincy", label: "Captaincy" },
      { href: "/attack", label: "Attack — xG and xA" },
      { href: "/defence", label: "Defence — DefCon" },
      { href: "/prices", label: "Price movement" },
    ],
  },
  {
    label: "Squad",
    items: [
      { href: "/players", label: "All players" },
      { href: "/team", label: "Optimal team" },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  async function signOut() {
    await getSupabaseBrowser().auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <>
      <div className="px-4 py-3 lg:hidden">
        <button
          onClick={() => setOpen(true)}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-gold px-4 py-2.5 text-sm font-bold text-ink"
        >
          <span aria-hidden>☰</span> Menu
        </button>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-[55] bg-black/35 lg:hidden"
          onClick={() => setOpen(false)}
          aria-hidden
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-[60] w-66 shrink-0 overflow-y-auto bg-page px-3 pt-4 pb-10 shadow-[2px_0_18px_rgba(0,0,0,.18)] transition-transform duration-200 lg:sticky lg:top-0 lg:z-0 lg:max-h-screen lg:w-58 lg:translate-x-0 lg:pt-6 lg:shadow-none ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <nav>
          {GROUPS.map((g) => (
            <div key={g.label} className="mb-4 last:mb-0">
              <h4 className="mb-1.5 px-2 font-display text-[10.5px] font-bold uppercase tracking-[0.1em] text-ink-2">
                {g.label}
              </h4>
              {g.items.map((item, i) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    prefetch={item.prefetch}
                    // Otherwise the drawer stays over the page you just opened.
                    onClick={() => setOpen(false)}
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-md px-3 py-2.5 text-sm leading-tight transition-colors lg:py-2 ${
                      active
                        ? "bg-pitch font-semibold text-white"
                        : "text-ink hover:bg-[#EDEAE0]"
                    }`}
                  >
                    <span
                      className={`inline-block w-[17px] text-[11px] ${
                        active ? "text-[#BFD9C9]" : "text-ink-3"
                      }`}
                    >
                      {i + 1}
                    </span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}

          <div className="mt-5 border-t border-hairline pt-4">
            <h4 className="mb-1.5 px-2 font-display text-[10.5px] font-bold uppercase tracking-[0.1em] text-ink-2">
              Account
            </h4>
            <button
              onClick={signOut}
              className="block w-full rounded-md px-3 py-2.5 text-left text-sm leading-tight text-ink transition-colors hover:bg-[#EDEAE0] lg:py-2"
            >
              <span className="inline-block w-[17px] text-[11px] text-ink-3">
                ↪
              </span>
              Sign out
            </button>
          </div>
        </nav>
      </aside>
    </>
  );
}
