# Deployment: Supabase auth + Vercel

The app is deployed as **two Vercel projects from this one repo**, both under the
`maartens-projects-8aef4975` scope:

| Vercel project | Root Directory | URL |
| --- | --- | --- |
| `plfantasy-web` | `frontend` | https://plfantasy-web.vercel.app |
| `plfantasy-api` | `backend` | https://plfantasy-api.vercel.app |

Login is Supabase email+password, invite-only. Every `/api/*` route except
`/api/health` requires a valid Supabase access token.

## How auth fits together

1. `frontend/src/app/login/page.tsx` signs in with `signInWithPassword`; the
   session lands in cookies via `@supabase/ssr`.
2. `frontend/src/proxy.ts` runs before every request (Next 16 renamed
   Middleware to Proxy), refreshes an expired token and redirects anonymous
   visitors to `/login`. This is an **optimistic** check only.
3. `frontend/src/lib/api.server.ts` is the data access layer: it verifies the
   session on every server-side data read and attaches the access token.
   `api.client.ts` does the same for browser-side reads.
4. `backend/app/auth.py` verifies the token signature against the project's
   JWKS (ES256) on every request. **This is the actual security boundary** —
   steps 1–3 are user experience.

Data still flows through FastAPI using privileged database credentials, so RLS
stays closed with no anon policies. Supabase is used for identity only.

## One-time Supabase setup (dashboard)

These cannot be done from the CLI or the API without a personal access token:

1. **Disable public signup** — Authentication → Sign In / Providers → Email:
   keep Email enabled, turn **off** *Allow new users to sign up*.
2. **Create each user** — Authentication → Users → *Add user* → *Create new
   user*, and **tick "Auto Confirm User"**. Auto-confirmed users need no email
   delivery, so no SMTP configuration is required. There is no self-service
   password reset in this app; reset passwords from this same screen.
3. Once the frontend URL is known, set Authentication → URL Configuration →
   Site URL to it.

## Deploying

`vercel login` opens a browser, so run these yourself. Deploy the **backend
first** — the frontend bakes `NEXT_PUBLIC_*` values in at build time, so it
needs the API URL to already exist.

```bash
npm i -g vercel        # already installed if you ran the setup
vercel login
```

### 1. Backend

```bash
cd backend
vercel link                                   # create project, e.g. plfantasy-api
vercel env add DATABASE_URL production        # TRANSACTION pooler, port 6543 (see below)
vercel env add SUPABASE_URL production        # https://<ref>.supabase.co
vercel env add CORS_ORIGINS production        # https://plfantasy-web.vercel.app,http://localhost:3000
vercel env add CORS_ORIGIN_REGEX production   # see below
vercel deploy --prod
```

`CORS_ORIGIN_REGEX` exists so preview deployments are allowed too. Watch the
URL shape here: Vercel **truncates the project name** in generated URLs, so a
`plfantasy-web` deployment is served from `plfantasy-<hash>-<scope>.vercel.app`,
not `plfantasy-web-<hash>-…`. The working value is

```
^https://plfantasy-[a-z0-9]+-maartens-projects-8aef4975\.vercel\.app$
```

Scoping it to the account slug rather than using a bare `.*\.vercel\.app` keeps
unrelated Vercel sites from being allowed to call the API.

`DATABASE_URL` must be the **transaction** pooler string from Supabase →
Connect, on port **6543** (not the 5432 session pooler used locally):

```
postgresql://postgres.<ref>:<password>@aws-<region>.pooler.supabase.com:6543/postgres
```

`backend/app/db.py` detects Vercel via the `VERCEL` env var and switches to
`NullPool` with `prepare_threshold=None`, which transaction pooling requires.

Smoke test:

```bash
curl https://<api>.vercel.app/api/health          # 200 {"status":"ok"}
curl -i https://<api>.vercel.app/api/meta         # 401
curl "https://<api>.vercel.app/api/optimal-team?budget=100&horizon=3" \
  -H "Authorization: Bearer <token>"              # 200 (see "Getting a token")
```

**Check the build log** for two things: that dependencies installed from
`requirements.txt` with pip (not resolved from `pyproject.toml`/`uv.lock`), and
the final bundle size. `backend/.vercelignore` hides the uv files precisely so
the full ML dependency tree (LightGBM, pandas, scikit-learn) stays out — it
would exceed Vercel's 250 MB function limit. `MODEL_VERSION` lives in
`backend/app/constants.py` so no API module imports `ml/`.

### 2. Frontend

```bash
cd frontend
vercel link                                            # e.g. plfantasy-web
vercel env add NEXT_PUBLIC_API_URL production          # https://<api>.vercel.app
vercel env add NEXT_PUBLIC_SUPABASE_URL production
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production
vercel deploy --prod
```

### 3. Redeploys

Changing any backend env var needs `vercel deploy --prod` from `backend/` to
take effect. Changing a `NEXT_PUBLIC_*` var needs a frontend redeploy, because
those are inlined at build time.

### 4. Optional: deploy on git push

In the Vercel dashboard, connect both projects to the GitHub repo and set
**Root Directory** to `frontend` and `backend` respectively. Root Directory
cannot be set from the CLI. Add the same env vars to the *Preview* environment
if you want preview deployments to work.

## Environment variables

| Variable | Frontend | Backend | Local file |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | ✔ | | `frontend/.env.local` |
| `NEXT_PUBLIC_SUPABASE_URL` | ✔ | | `frontend/.env.local` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✔ | | `frontend/.env.local` |
| `DATABASE_URL` | | ✔ | `backend/.env` |
| `SUPABASE_URL` | | ✔ | `backend/.env` |
| `CORS_ORIGINS` | | ✔ | `backend/.env` |
| `CORS_ORIGIN_REGEX` | | ✔ | — |
| `SUPABASE_JWT_SECRET` | | only legacy HS256 projects | — |

`NEXT_PUBLIC_*` values are inlined at build time: changing one requires a
redeploy, and all three are visible to anyone who loads the page. The
publishable/anon key is designed for that; never put a service role key there.

## Getting a token (for curl)

Sign in to the deployed app, then in the browser console:

```js
JSON.parse(
  Object.entries(localStorage).find(([k]) => k.includes("auth-token"))[1]
).access_token
```

## Production smoke test

- Visiting the site while signed out redirects to `/login`.
- Signing in lands on the dashboard with the header meta strip populated.
- All nine routes render: `/`, `/players`, `/players/[code]`, `/teams`,
  `/captaincy`, `/attack`, `/defence`, `/prices`, `/team`.
- Network tab shows `Authorization: Bearer …` on the cross-origin API calls and
  no CORS errors.
- Sign out returns to `/login` and the dashboard is gated again.
- A preview deployment URL is accepted by `CORS_ORIGIN_REGEX`.

## Known risks

- **PuLP/CBC in serverless.** `/api/optimal-team` solves an ILP using PuLP's
  bundled CBC binary. `vercel.json` allows 60s and 1024 MB for headroom. If it
  proves unreliable, switch `optimizer/ilp.py` to the HiGHS solver
  (`highspy`, a pure wheel with no external binary).
- **The rewrite in `backend/vercel.json`** sends every path to
  `api/index.py` while FastAPI still sees the original `/api/...` path. If
  routes 404 after deploy, that rewrite is the thing to check first; the
  fallback is the legacy `builds`/`routes` form of the same config.
- **The data pipeline stays local.** `backend/pipeline/` and `ml/` are excluded
  from the deployment; the weekly refresh still runs from your machine and
  writes to Supabase over `DATABASE_URL`.
