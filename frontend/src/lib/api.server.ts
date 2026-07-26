import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";
import { createApi } from "./api";
import { createSupabaseServer } from "./supabase/server";

/** Data access layer: every server-side data request goes through this, so the
 *  session is verified wherever the API is read. proxy.ts only does an
 *  optimistic cookie check, which is not enough on its own.
 *
 *  `cache` dedupes the verification across all components in one render pass. */
const requireSession = cache(async () => {
  const supabase = await createSupabaseServer();

  const { data: claims, error } = await supabase.auth.getClaims();
  if (error || !claims?.claims) redirect("/login");

  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) redirect("/login");

  return session;
});

/** Server-side fetch needs an absolute URL, so unlike the browser client this
 *  cannot use a relative path. On Vercel the API lives in the same deployment,
 *  so VERCEL_URL points at the right one for previews as well as production. */
function baseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "http://localhost:8000";
}

export const api = createApi(
  async () => (await requireSession()).access_token,
  // The token verified above was rejected by the API, so the session is stale.
  () => redirect("/login"),
  baseUrl(),
);
