# Deployment: Supabase auth + Vercel

Everything runs as **one Vercel project** — `plfantasy`, at
https://plfantasy.vercel.app — using [Vercel
Services](https://vercel.com/docs/services), which lets a single project build
several apps with different runtimes from one repo.

| Service | Root | Runtime | Serves |
| --- | --- | --- | --- |
| `web` | `frontend/` | Next.js | Everything except `/api/*` |
| `api` | `backend/` | Python | `/api/*` (FastAPI, entrypoint `app.main:app`) |

Routing lives in the root [`vercel.json`](../vercel.json): the first rewrite
sends `/api/(.*)` to the `api` service, the second sends everything else to
`web`. Services receive the **original path**, so FastAPI still sees
`/api/health`. Routing into a service is final — no fallback between services.

Because both share one domain, browser requests to the API are same-origin:
**no CORS is involved in production**, and no API hostname is baked into the
client bundle. `CORS_ORIGINS` only matters for local development, where the
frontend is on port 3000 and the API on 8000.

Login is Supabase email+password, invite-only. Every `/api/*` route except
`/api/health` requires a valid Supabase access token.

## How auth fits together

1. [`login/page.tsx`](../frontend/src/app/login/page.tsx) signs in with
   `signInWithPassword`; the session lands in cookies via `@supabase/ssr`.
2. [`proxy.ts`](../frontend/src/proxy.ts) runs before every request (Next 16
   renamed Middleware to Proxy), refreshes an expired token and redirects
   anonymous visitors to `/login`. An **optimistic** check only.
3. [`api.server.ts`](../frontend/src/lib/api.server.ts) is the data access
   layer: it verifies the session on every server-side read and attaches the
   token. [`api.client.ts`](../frontend/src/lib/api.client.ts) does the same in
   the browser, using a relative URL so previews hit their own API.
4. [`auth.py`](../backend/app/auth.py) verifies the token signature against the
   project's JWKS (ES256) on every request. **This is the actual security
   boundary** — steps 1–3 are user experience.

Data flows through FastAPI using privileged database credentials, so RLS stays
closed with no anon policies. Supabase is used for identity only.

## One-time Supabase setup (dashboard)

These cannot be done from the CLI without a personal access token:

1. **Disable public signup** — Authentication → Sign In / Providers → Email:
   keep Email enabled, turn **off** *Allow new users to sign up*.
2. **Create each user** — Authentication → Users → *Add user* → *Create new
   user*, and **tick "Auto Confirm User"**. Auto-confirmed users need no email
   delivery, so no SMTP setup is required. There is no self-service password
   reset in this app; reset passwords from the same screen.
3. Set Authentication → URL Configuration → Site URL to
   `https://plfantasy.vercel.app`.

## Deploying

```bash
vercel deploy --prod        # from the repo root
```

The project's Framework Preset must be **Services** for the root `vercel.json`
`services` key to take effect. Note that when `services` is present, top-level
`functions`, `buildCommand`, `outputDirectory` and `framework` are no longer
valid — they belong inside a service.

Redeploy after changing any environment variable. `NEXT_PUBLIC_*` values in
particular are inlined at build time, so a redeploy is the only way to change
them.

### Keeping the API bundle small

[`.vercelignore`](../.vercelignore) excludes `backend/pyproject.toml` and
`backend/uv.lock` so Vercel installs from `backend/requirements.txt` — the
API-only dependency set — instead of resolving the full ML tree (LightGBM,
pandas, scikit-learn), which would exceed the function size limit. It also drops
`backend/ml/`, `backend/pipeline/`, `backend/data/` and `backend/tests/`.

This works because `MODEL_VERSION` lives in
[`app/constants.py`](../backend/app/constants.py), so no API module imports
`ml/`. If you ever import from `ml/` inside `app/`, the deploy will break —
that indirection is load-bearing, not incidental.

Unlike Node, the Python runtime bundles **all files reachable at build time**
with no tree-shaking, which is why the exclusions are explicit.

## Environment variables

All on the single `plfantasy` project:

| Variable | Used by | Notes |
| --- | --- | --- |
| `DATABASE_URL` | api | **Transaction** pooler, port 6543 (see below) |
| `SUPABASE_URL` | api | JWT issuer + JWKS host |
| `SUPABASE_JWT_SECRET` | api | Only for legacy HS256 projects; unset here |
| `CORS_ORIGINS` | api | `http://localhost:3000` — local dev only |
| `NEXT_PUBLIC_SUPABASE_URL` | web | |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | web | Publishable key; safe to expose |
| `NEXT_PUBLIC_API_URL` | web | **Deliberately unset on Vercel** |

That last one matters: with it unset, the browser client falls back to a
relative URL (same-origin) and the server client falls back to `VERCEL_URL`, so
production and preview deployments each talk to their own API. Locally,
`frontend/.env.local` sets it to `http://localhost:8000`.

`DATABASE_URL` must be the **transaction** pooler string from Supabase →
Connect, on port **6543** (not the 5432 session pooler used locally):

```
postgresql://postgres.<ref>:<password>@aws-<region>.pooler.supabase.com:6543/postgres
```

[`app/db.py`](../backend/app/db.py) detects Vercel via the `VERCEL` env var and
switches to `NullPool` with `prepare_threshold=None`, which transaction pooling
requires — server-side prepared statements do not survive it.

## Smoke test

```bash
A=https://plfantasy.vercel.app
curl $A/api/health          # 200 {"status":"ok"}
curl -i $A/api/meta         # 401 (no token)
curl -i $A/                 # 307 -> /login when signed out
curl -i $A/players          # 307 -> /login?next=%2Fplayers
```

Signed in, check that all nine routes render (`/`, `/players`,
`/players/[code]`, `/teams`, `/captaincy`, `/attack`, `/defence`, `/prices`,
`/team`), that the header meta strip populates, and that sign out re-gates the
app. In the network tab the API calls should be same-origin `/api/...` requests
with an `Authorization: Bearer` header and no preflight.

To get a token for curl, sign in and run this in the browser console:

```js
JSON.parse(
  Object.entries(localStorage).find(([k]) => k.includes("auth-token"))[1]
).access_token
```

## Known risks

- **Services is in beta.** If it regresses, the fallback is two projects with
  Root Directories `frontend/` and `backend/`, linked via `relatedProjects`. In
  that shape the API is on its own domain, so `CORS_ORIGINS` and a
  `CORS_ORIGIN_REGEX` for preview URLs become load-bearing again — note that
  Vercel truncates the project name in generated URLs
  (`plfantasy-<hash>-<scope>.vercel.app`), which a naive regex will miss.
- **PuLP/CBC in serverless.** `/api/optimal-team` solves an ILP using PuLP's
  bundled CBC binary, with `maxDuration` raised to 60s. If it proves
  unreliable, switch [`optimizer/ilp.py`](../backend/optimizer/ilp.py) to the
  HiGHS solver (`highspy`, a pure wheel with no external binary).
- **The data pipeline stays local.** `backend/pipeline/` and `backend/ml/` are
  excluded from the deployment; the weekly refresh still runs from your machine
  and writes to Supabase over `DATABASE_URL`.
