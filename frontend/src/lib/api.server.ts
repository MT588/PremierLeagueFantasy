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
 *  cannot use a relative path.
 *
 *  This must be the project's public production domain, NOT VERCEL_URL. Under
 *  Vercel's default Deployment Protection every URL except the production alias
 *  redirects to an SSO page, so fetching VERCEL_URL server-side returns that
 *  HTML page instead of JSON. Preview deployments therefore read from the
 *  production API; only the browser (which uses a relative URL) stays on its
 *  own deployment. */
function baseUrl(): string {
  // Server-only, so it can differ from the relative URL the browser uses.
  if (process.env.API_ORIGIN) return process.env.API_ORIGIN;
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  // Safety net if API_ORIGIN is ever missing. This is populated at runtime even
  // though it does not show up in `vercel env pull`. Never use VERCEL_URL here.
  const production = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (production) return `https://${production}`;
  if (process.env.VERCEL) {
    throw new Error("API_ORIGIN is unset; set it to the API's public origin.");
  }
  return "http://localhost:8000";
}

export const api = createApi(
  async () => (await requireSession()).access_token,
  // The token verified above was rejected by the API, so the session is stale.
  () => redirect("/login"),
  baseUrl(),
);
