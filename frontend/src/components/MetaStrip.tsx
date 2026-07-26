import { unstable_rethrow } from "next/navigation";
import { api } from "@/lib/api.server";

/** Season / gameweek / model freshness line in the topbar. Replaces the
 *  source page's manual "refresh live data" button — our data is ingested
 *  server-side, so there is nothing for the browser to fetch or rate-limit. */
export async function MetaStrip() {
  let meta;
  try {
    meta = await api.meta();
  } catch (e) {
    // The API client redirects to /login by throwing; that must not be caught
    // here or an expired session would render as an API outage.
    unstable_rethrow(e);
    return (
      <div className="flex items-center gap-2 text-[13px] text-[#F0C9C4]">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#C0392B]" />
        API unreachable
      </div>
    );
  }
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
