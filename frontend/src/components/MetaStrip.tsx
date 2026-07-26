"use client";

import { useEffect, useState } from "react";
import { Meta } from "@/lib/api";
import { api } from "@/lib/api.client";

/** Season / gameweek / model freshness line in the topbar. Replaces the
 *  source page's manual "refresh live data" button — our data is ingested
 *  server-side, so there is nothing for the browser to fetch or rate-limit.
 *
 *  Read in the browser rather than on the server on purpose. This sits in the
 *  (app) layout, so a server-side session read here made every route under it
 *  dynamic — including the seven that are client components and hold no server
 *  data. Reading meta here instead lets those prerender, so they cost no
 *  function invocation. (It does not fix prefetching; see Sidebar.tsx.) */
export function MetaStrip() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // The API client sends an expired session to /login itself, so a rejection
    // here means the API is genuinely unreachable.
    api
      .meta()
      .then(setMeta)
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <div className="flex items-center gap-2 text-[13px] text-[#F0C9C4]">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#C0392B]" />
        API unreachable
      </div>
    );
  }

  if (!meta) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[#D9D5C4]">
      <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#4C9A6A]" />
      <span>Season {meta.season}</span>
      <span aria-hidden>·</span>
      <span>
        {meta.next_gameweek ? `Next: GW${meta.next_gameweek}` : "Season complete"}
      </span>
      <span aria-hidden>·</span>
      <span className="opacity-80">
        {meta.players_in_pool} players · {meta.predictions} predictions ·{" "}
        {meta.model_version}
      </span>
    </div>
  );
}
