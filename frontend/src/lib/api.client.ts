import { createApi } from "./api";
import { getSupabaseBrowser } from "./supabase/client";

export const api = createApi(
  async ({ forceRefresh }) => {
    const supabase = getSupabaseBrowser();
    if (forceRefresh) await supabase.auth.refreshSession();
    // getSession() refreshes on its own when the token is close to expiry.
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  },
  // Full page load rather than a router push, so the proxy re-evaluates and
  // every stale client cache is dropped.
  () => window.location.assign("/login"),
  // Empty on Vercel, where the API shares the frontend's domain: relative URLs
  // then resolve against whichever deployment is being viewed, previews
  // included, and no CORS preflight happens. Locally the API is on another
  // port, so .env.local sets this explicitly.
  process.env.NEXT_PUBLIC_API_URL ?? "",
);
