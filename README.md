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
- **Model**: single LightGBM regressor on leakage-safe rolling features (form,
  minutes, xG/xA per 90, fixture difficulty, team strengths, previous-season
  PPG). Backtest on held-out 2025-26: MAE 0.97 vs 1.05 for a last-5-average
  baseline, per-gameweek Spearman 0.71.
- **Optimizer**: PuLP/CBC integer program — 15-man squad, starting XI, captain
  and bench under budget, 2-5-5-3 squad shape, max 3 per club and a legal
  formation, maximizing predicted points over a 1–5 gameweek horizon.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+, Postgres
(local or a [Supabase](https://supabase.com) project).

```bash
# 1. database
createdb plfantasy
psql -d plfantasy -f supabase/migrations/0001_core_schema.sql
#    (on Supabase: apply the same file via the SQL editor or MCP apply_migration)

# 2. backend config — set DATABASE_URL (see .env.example)
cp .env.example backend/.env

# 3. install + load data (downloads ~90MB of CSVs, a few minutes)
cd backend
uv sync
uv run python -m pipeline.run_pipeline --all      # historical + live sync

# 4. train + predict
uv run python -m ml.train                          # prints backtest report
uv run python -m ml.predict --horizon 5            # writes predictions table

# 5. run the API
uv run uvicorn app.main:app --port 8000

# 6. run the web app
cd ../frontend
npm install
npm run dev                                        # http://localhost:3000
```

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
uv run python -m pipeline.run_pipeline --init --all   # schema + 5 seasons + live sync (~5 min)
uv run python -m ml.train                             # retrain (~1 min)
uv run python -m ml.predict --horizon 5               # write predictions
```

`--init` applies `supabase/migrations/*.sql` and is safe to re-run; the whole
pipeline is idempotent, so re-running after a pause just tops up whatever is
missing. RLS is enabled with no anon policies — only the backend (which
connects with database credentials) can read the tables.

## Weekly refresh during the season

```bash
cd backend
uv run python -m pipeline.run_pipeline --live      # new results, prices, flags
uv run python -m ml.predict --horizon 5            # refresh predictions
```

Retrain (`uv run python -m ml.train`) occasionally — e.g. monthly — so the
model sees the newest completed gameweeks.

## Tests

```bash
cd backend && uv run pytest        # optimizer rules + API smoke tests
```

## API

`GET /api/meta`, `/api/teams`, `/api/players`, `/api/players/{code}`,
`/api/predictions?gameweek=`, `/api/optimal-team?budget=100&horizon=3` —
interactive docs at `http://localhost:8000/docs`.
