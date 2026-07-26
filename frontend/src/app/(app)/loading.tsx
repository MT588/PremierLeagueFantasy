/** Skeleton shown while a page under (app) loads.
 *
 *  Every link carries prefetch={false} while prefetching is broken in
 *  production (see Sidebar.tsx), so nothing is warm on click. It barely
 *  registers on the static routes; it earns its keep on / and
 *  /players/[code], which are force-dynamic and wait on the API. */
export default function Loading() {
  return (
    <div className="space-y-4">
      <div className="h-7 w-56 animate-pulse rounded bg-hairline" />
      <div className="h-40 animate-pulse rounded-[10px] bg-hairline" />
      <div className="h-40 animate-pulse rounded-[10px] bg-hairline" />
    </div>
  );
}
