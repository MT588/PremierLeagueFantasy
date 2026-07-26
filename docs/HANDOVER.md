# Session handover — FPL Analytics v2 (July 26, 2026)

Written for resuming this project in a fresh session (any model). Read this
top to bottom before touching anything; it reflects the exact state at the
end of the build session.

## What this project is

Full-stack FPL analytics on branch `claude/codebase-scan-ko44ro`:
- `backend/` — Python 3.12 (uv): data pipeline, two-stage LightGBM prediction
  model, PuLP squad optimizer, FastAPI.
- `frontend/` — Next.js 16 + Tailwind (dark theme), 4 pages.
- `supabase/migrations/` — plain-SQL schema (0001 core, 0002 external sources).
- `docs/` — this file, the football-data.org API key setup, evaluation reports.

## State: what is DONE and verified

**v1 (complete, pushed):** 5 seasons of FPL history (2021-22 → 2025-26,
139k player-gameweek rows), live 2026-27 sync, single-stage model, optimizer,
API, web app.

**v2 (complete locally, all code committed):**
1. **External data ingested** (all idempotent, all cached under
   `backend/data/raw/` — gitignored, refetchable):
   - ClubElo daily strength ratings (as-of lookup verified for every fixture)
   - football-data.co.uk odds (100% of 1,900 finished fixtures matched)
   - Understat: **115,972 cross-league player-match xG rows for 1,259
     players**, identity-matched at 98.2–98.9% minutes-weighted per season
     (fuzzy token_set matching + `backend/data/curated/understat_overrides.csv`)
   - International load: WC2026 (Spain won; squads + knockout progress),
     WC2022, EURO2024, COPA2024 from Wikipedia (658 player-tournament rows)
   - Curated: manager stints 2021→2026 (gap-free vs every fixture),
     European-competition flags, set-piece duties, birth dates
2. **Feature package** `backend/ml/features/` — 9 groups, 76 features, all
   leakage-tested (future-mutation test in `tests/test_features_v2.py`).
3. **Model** — 3-class minutes classifier × points-given-start regressor +
   empirical cameo means. **Shipped feature set = form + meta + career +
   understat + setpiece (54 features)**, selected by ablation
   (`docs/ablation_v2.md`): understat is the biggest win (−0.011 MAE);
   opponent/market/schedule/manager groups are computed but excluded from the
   points model (they added noise; minutes model still uses schedule/manager/meta).
4. **Walk-forward results** (`docs/metrics_lgbm-v2.json`): v2 vs v1-retrained
   MAE 0.951 vs 0.964 (2025-26 fold), 0.978 vs 0.988 (2024-25). Rank corr
   within noise (−0.0017; seed std ±0.0005, season sampling ±0.004). Fold
   2023-24 v1 was slightly better on MAE (less training data) — honest caveat.
5. **Predictions written**: 2,790 rows (GW1-5 of 2026-27) under
   `model_version='lgbm-v2'` with `p_start`, `p_cameo` and SHAP `drivers`
   jsonb. Haaland GW1 = 6.03 pts driven by npxG/90 — face-valid.
6. **API + UI code**: model-version-filtered queries, availability badges,
   top-10 per position, "what drives this prediction" panel. Frontend builds
   clean; **21/21 backend tests pass**; ruff clean.

## What REMAINS (in order)

1. **Playwright UI verification** — restart both servers, browse all 4 pages,
   screenshot, check console errors (script pattern in scratchpad from v1 —
   recreate: chromium at `/opt/pw-browsers/chromium`, pages: `/`, `/players`,
   `/players/{code}`, `/team`). Servers:
   ```bash
   cd backend && uv run uvicorn app.main:app --port 8000 &
   cd frontend && npm run build && npm run start -- --port 3000 &
   ```
2. **README refresh** — the top-level README still describes v1 commands.
   Update: `--all` now includes curated/clubelo/odds/understat/international;
   train with `python -m ml.train_v2`; predict with `python -m ml.predict_v2`;
   mention ablation + docs/ artifacts. (v1 `ml.train`/`ml.predict` still work.)
3. **Final commit + push** (see Git notes below).
4. **Optimizer sanity check vs v2** — `/api/optimal-team` already consumes
   v2 predictions via model-version filter; eyeball the squad once servers run.

## Deferred / waiting on the user

- **football-data.org API key** — see `docs/FOOTBALL_DATA_API_SETUP.md`.
  Wikipedia squad-proxy is in place; the exact-minutes source
  (`FootballDataOrgSource.load` in `backend/pipeline/ingest_international.py`)
  is a deliberate `NotImplementedError` stub until the key exists.
- **Supabase migration** — user's free-tier project is likely paused.
  Everything rebuilds from sources: set `DATABASE_URL` in `backend/.env`,
  then `uv run python -m pipeline.run_pipeline --init --all` (~45 min, mostly
  Understat; all raw responses re-download unless `backend/data/raw/` is
  carried over), then `ml.train_v2` + `ml.predict_v2`. README has the steps.
- **Betting-site integration** — explicitly out of scope ("later").

## Environment gotchas (this container is ephemeral!)

- **Local Postgres 16** holds the working DB (`plfantasy`, user/pass
  postgres/postgres). Start with `pg_ctlcluster 16 main start` (it does NOT
  auto-start after container restarts). If the container is gone, the DB is
  gone — rebuild via the pipeline (sources are all public).
- **Model artifacts are gitignored** (`backend/ml/artifacts/`): retrain with
  `uv run python -m ml.train_v2` (~6 min) then `uv run python -m ml.predict_v2
  --horizon 5`. Evaluation reports are preserved in `docs/`.
- **Understat cache** (~1,300 JSON files) is gitignored; refetching takes
  ~35 min at the polite 1.1s/request throttle. The ingest is resumable.
- **ClubElo API is plain HTTP** (https broken) and throws transient 503s —
  the ingester retries; a header-only CSV is a transient failure, not "no data".
- **v1 model files** (`ml/train.py`, `ml/predict.py`, `ml/features_v1.py`)
  are kept for the regression test `tests/test_features_v2.py::test_v1_features_reproduce`.

## Git notes

- Branch: `claude/codebase-scan-ko44ro`, all work committed and pushed
  through "v2 phases 6-8 code". Local commits after that may exist — check
  `git log origin/claude/codebase-scan-ko44ro..HEAD`.
- **Commits must be SSH-signed**: `git config user.email noreply@anthropic.com
  && git config user.name Claude`, and commit with `-S` explicitly (plain
  commits came out unsigned in this container even with commit.gpgsign=true;
  a stop hook rejects unsigned/wrong-identity commits). To fix a batch:
  `git rebase --exec "git commit --amend --no-edit --reset-author -S" origin/claude/codebase-scan-ko44ro`.
- No PR exists yet; the user has not asked for one.

## Key design decisions (don't re-litigate without cause)

- Player/team identity = stable FPL `code`, never per-season element ids.
- Betting odds calibrate an Elo→probability map (`ml/elo_prob.py`,
  params in `docs/elo_prob_params.json`); odds are never direct features
  (future fixtures have none — train/inference consistency).
- `player_seasons.status` is a season-end snapshot for historical seasons →
  availability is an inference-time hard gate, never a training feature.
- Acceptance gate = material MAE win + rho within 0.005 tolerance (rationale
  documented in `ml/train_v2.py` — strict both-metrics dominance is noise-hostile).
- FPL 2024-25 "assistant manager" elements (position 5) are excluded everywhere.
