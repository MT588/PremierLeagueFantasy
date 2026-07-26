# PL Fantasy Analytics

Full-stack Fantasy Premier League analytics: five seasons of historical data,
a LightGBM model that predicts every player's points for the upcoming
gameweeks, and a web app that shows player ratings and solves the optimal
squad under the official FPL rules.

## Architecture

```
backend/    Python 3.12 (uv) — FastAPI, data pipeline, ML, ILP optimizer
frontend/   Next.js 16 + Tailwind — dashboard, player explorer, optimal team
supabase/   SQL migrations (plain Postgres, works on Supabase or local)
```

- **Data**: historical seasons (2021-22 → 2025-26) from
  [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League),
  current season synced live from the official FPL API. Players and teams are
  keyed on their stable cross-season `code`, not the per-season element id.
- **Model (v2)**: two-stage LightGBM — a 3-class minutes model (out/cameo/
  start) combined with a points-given-start regressor. Features span rolling
  form, multi-season class, Understat shot quality (cross-league for new
  signings, xG backfill for 2021-22), set-piece duties, plus ClubElo/manager/
  schedule/international-load context for the minutes stage. Feature groups
  selected by ablation (docs/ablation_v2.md). Walk-forward on 2025-26:
  MAE 0.951 vs 1.05 last-5 baseline, per-GW Spearman 0.72; per-prediction
  SHAP drivers stored for the UI. External sources: ClubElo Elo ratings,
  football-data.co.uk odds (calibrating an Elo→probability map), Understat
  (6 leagues), Wikipedia squads/manager data. See docs/HANDOVER.md for the
  full state of the v2 build.
- **Optimizer**: PuLP/CBC integer program — 15-man squad, starting XI, captain
  and bench under budget, 2-5-5-3 squad shape, max 3 per club and a legal
  formation, maximizing predicted points over a 1–5 gameweek horizon.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+, Postgres
(local or a [Supabase](https://supabase.com) project).

```bash
# 1. database
createdb plfantasy

# 2. backend config — set DATABASE_URL (see .env.example)
cp .env.example backend/.env

# 3. install + load data (~45 min on the first run; raw downloads are cached)
cd backend
uv sync
uv run python -m pipeline.run_pipeline --init --all

# 4. train + predict (v2: two-stage model, walk-forward eval, SHAP drivers)
uv run python -m ml.train_v2                       # prints per-fold report, saves artifacts
uv run python -m ml.predict_v2 --horizon 5         # writes predictions with drivers

# 5. run the API
uv run uvicorn app.main:app --port 8000

# 6. run the web app
cd ../frontend
npm install
npm run dev                                        # http://localhost:3000
```

`--all` loads historical and live FPL data, curated manager/set-piece/European
competition data, ClubElo, football-data.co.uk odds, Understat, and
international-tournament load. The slowest part is fetching Understat xG for
about 1,300 players at a polite request rate. Each loader is idempotent and
stores refetchable raw responses under `backend/data/raw/`.

## Loading into Supabase

Free-tier Supabase projects pause after inactivity — everything here rebuilds
from public sources, so nothing is lost. When the project is active again:

1. **Restore/unpause** the project in the Supabase dashboard (or create a new
   one — no existing schema is required).
2. Copy the **connection string** from *Project Settings → Database* (either
   the direct connection or the session pooler; the `postgres://...` string
   can be pasted as-is).
3. Point the backend at it and load everything with one command:

```bash
cd backend
echo 'DATABASE_URL=postgres://postgres.<ref>:<password>@<host>:5432/postgres' > .env
uv run python -m pipeline.run_pipeline --init --all   # schema + all data sources
uv run python -m ml.train_v2                          # train/evaluate two-stage model
uv run python -m ml.predict_v2 --horizon 5            # write v2 predictions + drivers
```

`--init` applies `supabase/migrations/*.sql` and is safe to re-run; the whole
pipeline is idempotent, so re-running after a pause just tops up whatever is
missing. RLS is enabled with no anon policies — only the backend (which
connects with database credentials) can read the tables.

## Weekly refresh during the season

```bash
cd backend
uv run python -m pipeline.run_pipeline --live      # new results, prices, flags
uv run python -m ml.predict_v2 --horizon 5         # refresh v2 predictions
```

Retrain (`uv run python -m ml.train_v2`) occasionally — e.g. monthly — so the
model sees the newest completed gameweeks.

The original single-stage workflow remains available as `python -m ml.train`
and `python -m ml.predict` for regression comparisons.

## Authentication

The dashboard sits behind Supabase email+password login (invite-only — accounts
are created in the Supabase dashboard, public signup is off). Every `/api/*`
route except `/api/health` requires a valid Supabase access token, verified
against the project's JWKS in `backend/app/auth.py`.

Local setup: add `SUPABASE_URL` to `backend/.env`, and
`NEXT_PUBLIC_SUPABASE_URL` plus `NEXT_PUBLIC_SUPABASE_ANON_KEY` to
`frontend/.env.local`. See `.env.example`.

## Deployment

Frontend and backend deploy as two Vercel projects from this repo — see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The data pipeline stays local.

## Tests

```bash
cd backend && uv run pytest        # optimizer rules + API smoke tests + auth
```

## Evaluation artifacts

- `docs/ablation_v2.md` — feature-group ablation and shipped feature set
- `docs/metrics_lgbm-v2.json` — walk-forward v2 metrics
- `docs/metrics_lgbm-v1-retrained.json` — like-for-like v1 comparison
- `docs/elo_prob_params.json` — fitted Elo-to-result-probability calibration
- `docs/FOOTBALL_DATA_API_SETUP.md` — optional football-data.org exact-minutes setup

## API

`GET /api/meta`, `/api/teams`, `/api/players`, `/api/players/{code}`,
`/api/predictions?gameweek=`, `/api/optimal-team?budget=100&horizon=3` —
interactive docs at `http://localhost:8000/docs`.
