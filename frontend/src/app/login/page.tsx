"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { getSupabaseBrowser } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPending(true);
    setError(null);

    const { error } = await getSupabaseBrowser().auth.signInWithPassword({
      email,
      password,
    });
    if (error) {
      setError("Those credentials did not work. Check your email and password.");
      setPending(false);
      return;
    }

    // Only follow same-origin paths, so ?next= can't be used as an open redirect.
    const next = new URLSearchParams(window.location.search).get("next");
    router.replace(next?.startsWith("/") ? next : "/");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4">
      <div className="w-full max-w-sm">
        <div className="mb-5 text-center">
          <div className="font-display text-[11px] font-bold uppercase tracking-[0.12em] text-gold">
            Fantasy Premier League
          </div>
          <h1 className="font-display text-[22px] font-black tracking-tight text-ink">
            Fixture &amp; Form Dashboard
          </h1>
        </div>

        <form
          onSubmit={onSubmit}
          className="rounded-xl border border-hairline bg-surface p-6 shadow-sm"
        >
          <h2 className="mb-4 font-display text-[15px] font-bold text-ink">Sign in</h2>

          <label
            htmlFor="email"
            className="mb-1 block text-[12px] font-semibold text-ink-2"
          >
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mb-3.5 w-full rounded-md border border-grid bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:border-pitch"
          />

          <label
            htmlFor="password"
            className="mb-1 block text-[12px] font-semibold text-ink-2"
          >
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-4 w-full rounded-md border border-grid bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:border-pitch"
          />

          {error && (
            <p
              role="alert"
              className="mb-4 rounded-md border border-[#E3B7B1] bg-[#FBF0EE] px-3 py-2 text-[12.5px] text-[#8C2F22]"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={pending}
            className="w-full rounded-md bg-pitch px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-pitch-light disabled:opacity-60"
          >
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-4 text-center text-[11.5px] leading-relaxed text-ink-2">
          Accounts are created by invitation. Ask the dashboard owner for access.
        </p>
      </div>
    </div>
  );
}
