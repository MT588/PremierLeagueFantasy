/** Skeleton shown while a server-rendered page under (app) is being built.
 *
 *  Only / and /players/[code] reach it — the rest of the group is static and
 *  prefetched, so it swaps in without a server roundtrip. Those two are
 *  force-dynamic and their links carry prefetch={false}, so without this the
 *  browser would sit on the old page with no feedback while the API answers. */
export default function Loading() {
  return (
    <div className="space-y-4">
      <div className="h-7 w-56 animate-pulse rounded bg-hairline" />
      <div className="h-40 animate-pulse rounded-[10px] bg-hairline" />
      <div className="h-40 animate-pulse rounded-[10px] bg-hairline" />
    </div>
  );
}
