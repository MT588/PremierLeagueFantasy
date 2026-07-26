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
);
