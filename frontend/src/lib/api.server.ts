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

export const api = createApi(
  async () => (await requireSession()).access_token,
  // The token verified above was rejected by the API, so the session is stale.
  () => redirect("/login"),
);
