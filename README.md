# PL Fantasy Analytics

Full-stack Fantasy Premier League analytics: five seasons of historical data,
a model that predicts the full distribution of every player's points for the
upcoming gameweeks, and a web app that shows player ratings and solves the
optimal squad under the official FPL rules.

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
- **Model (v3)**: per-component expected points. A 3-class minutes model
  (out/cameo/start) feeds seven component models — goals, assists, team goals
  conceded (clean sheets), saves, defensive contributions, bonus and cards —
  and `ml/scoring.py` prices them with the official scoring matrix. The
  arithmetic is exact rather than fitted: it reproduces `total_points` for
  every one of the ~139k archived rows, which is a test gate. A Monte-Carlo
  simulation over those components produces the full points distribution per
  player-gameweek — P(blank), P(return), P(haul) and p10/p50/p90 — so the app
  can rank on the ceiling rather than only the mean.

  Features span rolling form, empirical-Bayes shrunk form (the season-boundary
  fix), multi-season class, Understat shot quality, set-piece duties, plus
  ClubElo/manager/schedule/international-load context. Walk-forward against v2
  retrained under the identical protocol: v3 wins MAE on 3 of 4 folds
  (2025-26: 0.951 vs 0.957), P(haul) calibration on 4 of 4, and tail RMSE on
  every fold where the defensive-contribution component is fittable. It trails
  v2 on rank correlation by 0.0005–0.0035 per fold, which the acceptance gate
  admits as a tolerance — see `ml/train_v3.py` for why. Per-prediction
  component breakdowns are stored for the UI.

  External sources: ClubElo Elo ratings, football-data.co.uk odds (calibrating
  an Elo→probability map), Understat (6 leagues), Wikipedia squads, manager
  data and tournament line-ups (exact World Cup / Euro minutes parsed from
  match line-up tables). See docs/HANDOVER.md for the full state of the build.

  v1 (single-stage) and v2 (two-stage) remain runnable as comparison baselines;
  predictions are keyed by `model_version`, so switching generations is a
  one-line change in `backend/app/constants.py`.
- **Optimizer**: PuLP/CBC integer program over a 1–10 gameweek horizon (default
  5). It picks the opening 15-man squad under budget, 2-5-5-3 squad shape, max 3
  per club and a legal formation, then plans each following week: the starting
  XI and captain are re-picked for free, transfers come out of the free
  allowance (one a gameweek, banked up to five, no points hits). Only the XI and
  the captain double score, and a small bonus on banked transfers makes the plan
  save them up for a batch rather than spend one every week.

  The horizon is capped by how far predictions reach — plan over ten gameweeks
  and `ml.predict_v3 --horizon 10` has to have been run, otherwise the endpoint
  plans over the weeks it has. Cost scales steeply with length: five gameweeks
  solve in a few seconds, ten take about half a minute.

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

# 4. train + predict (v3: components, distribution, walk-forward eval)
uv run python -m ml.elo_prob                       # fits the Elo->probability map first
uv run python -m ml.train_v3                       # per-fold report, acceptance gate, artifacts
uv run python -m ml.predict_v3 --horizon 10        # predictions + distribution + drivers

# 5. run the API
uv run uvicorn app.main:app --port 8000

# 6. run the web app
cd ../frontend
npm install
npm run dev                                        # http://localhost:3006
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
uv run python -m ml.elo_prob                          # Elo->probability calibration
uv run python -m ml.train_v3                          # train/evaluate the component model
uv run python -m ml.predict_v3 --horizon 10           # write v3 predictions + drivers
```

`ml/artifacts/` and `data/raw/` are gitignored, so after a clean checkout these
three commands must run in that order — the market features fail with a missing
`elo_prob_params.json` otherwise.

`--init` applies `supabase/migrations/*.sql` and is safe to re-run; the whole
pipeline is idempotent, so re-running after a pause just tops up whatever is
missing. RLS is enabled with no anon policies — only the backend (which
connects with database credentials) can read the tables.

## Weekly refresh during the season

```bash
cd backend
uv run python -m pipeline.run_pipeline --live      # new results, prices, flags
uv run python -m ml.predict_v3 --horizon 10        # refresh v3 predictions
```

Retrain (`uv run python -m ml.train_v3`) occasionally — e.g. monthly — so the
model sees the newest completed gameweeks. Retraining early in a season matters
more than it used to: the shrinkage weights that blend this season's form
against last season's prior are refitted from the training rows each time.

The earlier generations remain available for regression comparisons:
`ml.train`/`ml.predict` (v1, single-stage) and `ml.train_v2`/`ml.predict_v2`
(v2, two-stage).

## Authentication

The dashboard sits behind Supabase email+password login (invite-only — accounts
are created in the Supabase dashboard, public signup is off). Every `/api/*`
route except `/api/health` requires a valid Supabase access token, verified
against the project's JWKS in `backend/app/auth.py`.

Local setup: add `SUPABASE_URL` to `backend/.env`, and
`NEXT_PUBLIC_SUPABASE_URL` plus `NEXT_PUBLIC_SUPABASE_ANON_KEY` to
`frontend/.env.local`. See `.env.example`.

## Deployment

Live at **https://plfantasy.vercel.app**. Frontend and API deploy together as a
single Vercel project using Vercel Services — `frontend/` serves the app and
`backend/` serves `/api/*` from the same domain. See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The data pipeline stays local.

```bash
vercel deploy --prod        # from the repo root
```

## Tests

```bash
cd backend && uv run pytest        # optimizer, API, auth, scoring, features, distribution
```

The two feature suites rebuild the training frame several times to prove no
feature can see the future, so a full run takes around 15 minutes. To skip them:

```bash
uv run pytest --ignore=tests/test_features_v2.py --ignore=tests/test_features_v3.py
```

## Evaluation artifacts

- `docs/report_v3.md` — per-fold v3 vs v2 comparison, calibration, acceptance
- `docs/metrics_lgbm-v3.json` — walk-forward v3 metrics
- `docs/ablation_v3.md` — v3 feature-group ablation, per fold
- `docs/form_fix_v3.json` — the season-boundary form fix, measured in isolation
- `docs/ablation_v2.md` — v2 feature-group ablation and shipped feature set
- `docs/metrics_lgbm-v2.json` — walk-forward v2 metrics
- `docs/metrics_lgbm-v1-retrained.json` — like-for-like v1 comparison
- `docs/elo_prob_params.json` — fitted Elo-to-result-probability calibration
- `docs/FOOTBALL_DATA_API_SETUP.md` — optional football-data.org exact-minutes setup

## API

`GET /api/meta`, `/api/teams`, `/api/players`, `/api/players/{code}`,
`/api/predictions?gameweek=`, `/api/optimal-team?budget=100&horizon=5` —
interactive docs at `http://localhost:8000/docs`.
