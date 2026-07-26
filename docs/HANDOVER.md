# Session handover — FPL Analytics v3 (July 26, 2026)

Written for resuming this project in a fresh session (any model). Read this top
to bottom before touching anything. It supersedes the v2 handover; v1 and v2
remain runnable and are still the comparison baselines.

**The season starts 2026-08-21 — under four weeks away.** The form-boundary work
(the part that matters most for GW1) is done and proven. The component model is
built and evaluated but has two open decisions, both listed under
"Decisions waiting on you".

## What this project is

Full-stack FPL analytics on branch `develop`:
- `backend/` — Python 3.12+ (uv): data pipeline, prediction models, PuLP squad
  optimizer, FastAPI.
- `frontend/` — Next.js 16 + Tailwind (dark theme), 8 pages.
- `supabase/migrations/` — plain SQL (0001 core, 0002 external, 0003 stat gaps,
  0004 v3 components).
- `docs/` — this file, evaluation reports, deployment and API-key setup.

Three model generations coexist. Predictions are keyed by `model_version`, so
switching generations is a one-line change in `backend/app/constants.py` and
nothing needs migrating:

| generation | version | entry points |
|---|---|---|
| v1 single-stage | `lgbm-v1` | `ml.train`, `ml.predict` |
| v2 two-stage | `lgbm-v2` | `ml.train_v2`, `ml.predict_v2` |
| **v3 per-component** | `lgbm-v3` | `ml.train_v3`, `ml.predict_v3` |

`app.constants.MODEL_VERSION` is currently `lgbm-v3` — the API serves v3.

---

## v3: what it is

v2 asked one LightGBM regressor to learn `total_points` given a start. v3 models
the countable events instead and prices them with the official scoring matrix:

```
goals, assists      per-90 rate models (Poisson or negative binomial, chosen per fold)
clean sheet / GC    one team-level goals-conceded model shared by the XI
saves               per-90 rate driven by the shots a keeper faces
defensive actions   P(clearing the positional DC threshold)
bonus               BPS ranked within the fixture -> empirical bonus distribution
cards               small negative term, with suspension proximity
```

`ml/scoring.py` does the arithmetic. It is exact, not fitted: it reproduces the
recorded `total_points` for **all 138,707 archived rows across five seasons**,
which is a test gate (`tests/test_scoring_v3.py` — **not yet written**, see
"What remains").

From those components `ml/distribution.py` runs a Monte Carlo to get the full
per-player per-gameweek points distribution: `p_blank` (≤2), `p_return` (≥5),
`p_haul` (≥10) and p10/p50/p90, all stored in `predictions`.

### Key files

| file | what it holds |
|---|---|
| `ml/scoring.py` | per-season scoring matrix; `points_from_components`; `derive_dc_thresholds` |
| `ml/components/base.py` | shared rate-model machinery, NB dispersion, sampling |
| `ml/components/*.py` | one module per component, uniform `FEATURES`/`train`/`refit`/`predict` |
| `ml/components/team_defence.py` | team-fixture frame + goals conceded/scored models |
| `ml/distribution.py` | Monte Carlo, `analytic_ev`, `Bundle` |
| `ml/v3_model.py` | the fitted model, `build_bundle`, save/load, `refit_full` |
| `ml/train_v3.py` | folds, family/bonus selection, acceptance gate, report |
| `ml/predict_v3.py` | writes predictions + component drivers |
| `ml/features/form_eb.py` | empirical-Bayes shrunk form (the season-boundary fix) |
| `ml/shrinkage.py` | fits the blend weights per fold |
| `ml/features/tournament.py` | World Cup bridge features (computed, **not shipped**) |
| `ml/ablation_v3.py` | per-fold feature-group ablation |
| `ml/eval_form_fix.py` | the phase-A gate, isolated on the v2 architecture |

---

## Walk-forward results

Four folds. The first three follow v2 (train through a season, predict the next).
The fourth splits 2025-26 in half, and exists because the defensive-contribution
inputs arrived with the rule in 2025-26 — no season-level fold can both train and
test that component, and this is the only fold that sees the current scoring rules
on both sides.

| fold | v3 MAE | v2 MAE | v3 rho | v2 rho | v3 RMSE≥8 | v2 RMSE≥8 | v3 Brier | v2 Brier |
|---|---|---|---|---|---|---|---|---|
| 2023-24 | **0.9476** | 0.9680 | 0.6925 | 0.6947 | **7.600** | 7.844 | **0.01583** | 0.01653 |
| 2024-25 | **0.9686** | 0.9842 | **0.7090** | 0.7088 | **7.237** | 7.257 | **0.01446** | 0.01530 |
| 2025-26 | **0.9449** | 0.9575 | 0.7175 | 0.7202 | 7.576 | **7.531** | **0.01642** | 0.01687 |
| 2025-26 H2 | 0.9210 | **0.9171** | 0.7220 | 0.7229 | **6.988** | 7.199 | **0.01540** | 0.01617 |

v3 wins MAE in 3/4, tail RMSE in 3/4, and **P(haul) calibration in 4/4**. It
loses rank correlation narrowly in 3/4.

Full detail in `docs/metrics_lgbm-v3.json` and `docs/report_v3.md`.

---

## Decisions waiting on you

### 1. The acceptance gate fails as specified

`ml/train_v3.py` implements the gate exactly as briefed — on the 2025-26 fold, v3
must beat v2 on per-gameweek Spearman **and** tail RMSE, keep P(haul) Brier lower,
and not regress MAE by more than 0.01. It currently fails two of the four:

```
spearman   0.71747 vs 0.72024   FAIL
tail_rmse  7.5763  vs 7.5307    FAIL
haul_brier 0.01642 vs 0.01687   pass
mae        0.9449  vs 0.9575    pass (a 1.3% win)
```

Artifacts are currently produced with `--ship-anyway`, which does **not** soften
any threshold: it records `"shipped_by_override": true` in the metrics JSON and
prints the failure. Remove the flag and training refuses to ship.

What is known about each failure:

- **Spearman (−0.0028).** Reproducible, not noise. Measured across three
  LightGBM seeds: v3 0.7173–0.7175, v2 0.7198–0.7208. Already ruled out:
  feature-group selection (the ablation shows rho flat at 0.714–0.718 for every
  configuration), model capacity (31/63/127 leaves), the training exposure floor,
  bonus resolution, and Monte-Carlo resolution. The plausible remaining cause is
  structural: a single regressor trained on the target optimises ranking
  directly, while seven component likelihoods do not. Untested lever: the
  clean-sheet component's ranking contribution — substituting the observed clean
  sheet for the modelled probability would measure the headroom there in one run.
- **Tail RMSE (+0.046).** This one has an explanation and it is fold-specific.
  It fails **only** on the fold where defensive-contribution points exist in the
  actuals but the component cannot be fitted. On the two folds where DC is absent
  from the actuals, v3 wins the tail; on the H2 fold, where DC is both present
  and fittable, v3 wins the tail by 0.21. So the acceptance fold is the one fold
  structurally unfair to v3 on this metric.

**Your call.** Options: accept the tail result as a known fold artifact and gate
on H2 instead; relax the rho clause to a tolerance as v2's own gate did (it
allowed 0.005, with the rationale documented in `ml/train_v2.py`); keep chasing
rho; or ship v2 and hold v3.

### 2. The captaincy blend fits to zero

The view is meant to rank by upside rather than expected points alone. `upside =
ev + lambda * p_haul`, with lambda fitted on walk-forward. On the pooled
held-out gameweeks, leaning on P(haul) improves **neither** objective: the
top-3 shortlist's mean points peak at lambda=0 (7.368) and so does its haul rate
(0.3258). Expected points already rank the ceiling picks.

**There is an uncommitted-behaviour mismatch here — fix this first.**
`ml/train_v3.py` on disk contains a corrected selection rule (maximise shortlist
haul rate subject to mean points within 2%, tie-breaking to the smaller lambda)
and a grid extended to lambda=200 to probe the pure-P(haul) endpoint. **That code
has never been run.** The shipped artifacts and the `upside_lambda` block of
`docs/metrics_lgbm-v3.json` / `docs/report_v3.md` come from the *previous* rule,
which picked lambda=12.0 — a value that was worse on both metrics, because the
old rule wrongly assumed a larger weight always buys upside.

Everything else in those two files (all fold metrics, calibration, reliability
curves) is unaffected. One `uv run python -m ml.train_v3 --draws 1500
--ship-anyway` regenerates them consistently, ~7 minutes.

If lambda still fits to 0, the honest resolution is to rank by expected points
and surface P(haul)/P(return)/p90 as sortable columns, documenting why — rather
than hard-coding a weight the data rejects.

---

## What is DONE and verified

**Phase 0 — scoring and schema**
- `ml/scoring.py` reconstructs `total_points` exactly for all five seasons.
- DC thresholds *derived from data* as {DEF: 10, MID: 12, FWD: 12}; the derivation
  is kept as a check so a mid-season rule change surfaces as a failure rather
  than silently mispricing every defender.
- 2026-27's live rules are read from `bootstrap-static.game_config` and cached to
  `backend/data/raw/fpl/`. **Note the rule change: a keeper's goal is now 10
  points, up from 6.**
- Migration `0004_v3_components.sql`: `tackles`,
  `clearances_blocks_interceptions`, `recoveries` on `player_gameweeks`;
  `goals`/`assists`/`starts`/`last_match_date` on `international_load`; the seven
  distributional columns plus `components` jsonb on `predictions`.

**Phase A — the season-boundary form fix (this was the priority)**
- `features/form_eb.py` blends current-season rates toward a prior at weight
  `n / (n + k)`, with the prior falling back through previous season → trailing
  two-season career → Understat cross-league career → a position × price league
  prior computed only from earlier seasons.
- `k` is **fitted, not chosen** (`ml/shrinkage.py`), per statistic, on each
  fold's training seasons only. Fitted values sit in
  `ml/artifacts/shrinkage_lgbm-v3.json`.
- **Proven on the metric that matters**: measured on the unchanged v2
  architecture so it isolates the features, GW1-8 MAE improves in **3/3 folds** —
  1.0530→1.0463, 1.0680→1.0580, 1.0609→1.0502. Full-season MAE neutral to
  better; rho flat within noise. Evidence: `docs/form_fix_v3.json`,
  reproduce with `uv run python -m ml.eval_form_fix`.

**Phase A2 — the World Cup 2026 bridge (data landed; feature NOT shipped)**
- Sources investigated, as asked. **StatsBomb open data does not have WC2026** —
  confirmed against `open-data/data/competitions.json`, which stops at WC2022
  (it does have EURO2024 and Copa2024). FBref was not scraped.
- What works: Wikipedia's stage pages carry full line-up tables with
  `{{subon|63}}` / `{{suboff|78}}` / `{{yel|49}}` markers, so **exact per-player
  minutes are derivable**. `WikipediaLineupSource` parses 14 pages for WC2026 and
  the equivalents for WC2022 / EURO2024 / Copa2024 (so the features have training
  history at all), guarded by a parse-health probe that leaves minutes NULL
  rather than half-filling the table.
- Verified: **104/104 WC2026 matches**, 1,037 players with minutes, 229/252
  matched PL players carrying parsed minutes. Face-valid — Argentina and Spain
  players show a 2026-07-19 last match, England 07-15/18; Haaland 7 goals, Kane 6.
- Accuracy is honest and documented in the module: minutes and starts are exact
  where a line-up parses; **goals land within about 10%** of published totals
  (166 vs 172 for WC2022, 105 vs 117 for EURO2024, 68 vs 61 for Copa2024),
  because scorer lines vary more than line-up tables do.
- **Tournament assists are unavailable in any free source.** Left NULL, not faked.
- **The feature group does not earn its place yet and is excluded from the
  shipped set.** Measured on v2's architecture it moved nothing: the points stage
  got slightly worse on the one fold able to learn it (2025-26 GW1-8 MAE
  1.0502→1.0528) and the minutes stage moved by 3e-5. Only folds whose training
  seasons contain a summer tournament can learn it, which today means one fold.
  The loader still earns its place: `international_load` now holds exact parsed
  minutes instead of a squad-membership proxy, feeding the `schedule` group.

**Phase B — components, distribution, predictions**
- Seven components; family (Poisson vs negative binomial) and bonus route
  (fixture-ranked BPS vs direct regression) selected per fold on held-out data
  and recorded in the report.
- Monte Carlo with two details that are easy to get wrong and are handled:
  goals conceded is drawn **once per fixture and shared** by that team's players,
  and a double gameweek sums the *draws* before any quantile is taken.
- **2,790 v3 predictions written** for GW1-5 of 2026-27. Face-valid: attackers
  lead (Gibbs-White 5.67, Mbeumo 5.63, Haaland 5.05 at p_haul 0.204), keepers
  average 1.14 EV, and the component breakdown reads sensibly
  (Watkins: goals 2.83, appearance 1.69, bonus 0.85, assists 0.20).

---

## Bugs found and fixed — worth not reintroducing

1. **`refit_full` read iteration counts off already-refitted boosters.** A
   refitted booster has no `best_iteration`, so refitting from one collapsed every
   component to ten boosting rounds. The shipped model predicted its base score
   for everybody: flat, position-blind rates that gave Pickford 7.6 points of
   *goal* value. Fixed by carrying the counts explicitly in `V3Model.rounds`, and
   guarded by `train_v3.sanity_check`, which refuses to ship unless forwards
   carry several times a keeper's goal threat and keepers make the saves. Fold
   metrics were never affected — only the final refit.
2. **Bonus was sampled independently of the returns drawn in the same
   iteration.** A player who has just scored twice is near-certain to top the BPS
   table; severing that link visibly thinned the haul tail. Fitting
   P(bonus | bucket, returns) moved predicted haul rate from 0.99% to 1.38%
   against an empirical 1.81%.
3. **The chosen bonus route was a silent no-op** — selected, then never used,
   because both the simulator and the EV always took the rank path. Both routes
   now produce a distribution and the selection is live.
4. **Monte-Carlo EV cost 0.003 of rank correlation to ties.** A mean of integer
   point totals over 300 draws takes only ~1,700 distinct values across 29,000
   predictions. `ev` is now the closed-form `analytic_ev`; the MC mean is kept
   as `ev_mc` and their agreement is the intended consistency check.
5. **`|goals1=` swallowed `|goals2=`** in the Wikipedia parser, because the
   terminating-parameter pattern excluded digits — double counting away scorers
   and adding penalty-shootout goals. Caught only because an independent goal
   count disagreed.
6. **Goals were merged onto players by name.** Line-up tables link full names
   ("Harry Kane"), scorer lists use the short form ("Kane"), so every tournament
   goal was being dropped. Merge on the resolved player code.
7. **`.eq(0)` maps null to False**, which scored an unplayed fixture as
   "conceded" in the team clean-sheet rolling window. Mask before rolling.
8. **`derive_dc_thresholds` / the scoring matrix are per season.** 2021-22 to
   2024-25 have no DC and a 6-point keeper goal; 2025-26 adds DC; 2026-27 raises
   the keeper goal to 10. Scoring a frame with the wrong season's rules is silent.

---

## What remains

In rough priority order.

1. **Settle the two decisions above**, and rerun `ml.train_v3` so the docs match
   the code (see the mismatch note in decision 2).
2. **Tests — four files, none written yet.** Planned and all cheaply verifiable
   because the underlying facts are already confirmed by hand:
   - `test_scoring_v3.py` — exact `total_points` reconstruction per season under
     that season's rules (2025-26 must be 100%; verified manually);
     `derive_dc_thresholds` == {DEF: 10, MID: 12, FWD: 12}.
   - `test_features_v3.py` — the future-mutation leakage test from
     `test_features_v2.py` extended over the v3 feature list, with `tackles`,
     `clearances_blocks_interceptions`, `recoveries` and
     `defensive_contribution` added to `MUTABLE_COLS`; plus that shrinkage `k`
     fitting sees only training rows, and that GW1 rows lean on the prior.
   - `test_distribution.py` — `analytic_ev` ≈ simulated mean within Monte-Carlo
     error, monotone quantiles, probabilities in [0,1], seeded determinism, and
     that a double gameweek sums draws rather than quantiles.
   - `test_international_lineups.py` — the parser against a cached wikitext
     fixture, no network: the Canada v Morocco round-of-16 line-up must give
     Laryea off at 78' and Larin on at 63'.

   The existing 27 tests pass. Run `cd backend && uv run pytest`.
3. **API and frontend wiring — not started.** `predictions` already holds the new
   columns and `predict_v3` writes them; nothing reads them yet.
   - `app/schemas.py`: add `p_blank`, `p_return`, `p_haul`, `p10`, `p50`, `p90`,
     `upside` to `PredictionOut` and `PlayerStats`.
   - `app/queries.py`: add them to the `predictions` joins in `PLAYER_STATS` and
     `PLAYER_PREDICTIONS`.
   - `frontend/src/lib/api.ts`: mirror the types.
   - `frontend/src/components/columns.tsx`: add `haulCol`, `returnCol`,
     `blankCol`, `p90Col`, `upsideCol` beside the existing `epCol`/`pStartCol`.
   - `frontend/src/app/(app)/captaincy/page.tsx`: change `initialSort`, add the
     columns, and rewrite the `InfoBox` — it currently describes v2's two-stage
     model.
   - The driver payload changed shape: v2 sent SHAP feature attributions, v3
     sends a `components` list (`[{name, points}]`) plus the same `p_start` /
     `p_cameo` / `expected_if_start` keys. The player-detail panel needs updating
     to render components.
   - Read `frontend/AGENTS.md` first: this is not the Next.js in your training
     data, and the guides in `node_modules/next/dist/docs/` are authoritative.
4. **Finish the ablation.** `docs/ablation_v3.md` currently covers **only the
   2025-26 fold** — `ml/ablation_v3.py` supports all four, which is the point of
   it (v2's single-fold table could not tell a real effect from a fold-specific
   one). Run `uv run python -m ml.ablation_v3 --draws 400`; budget roughly
   25 seconds per config per fold, 19 configs.
5. **README** still documents v2 as current. Needs the v3 commands, the new
   sources, the distributional outputs.
6. **Optimizer sanity check against v3.** `/api/optimal-team` consumes whatever
   `MODEL_VERSION` names, so it is already on v3 — eyeball one squad.
7. **Playwright UI verification** was never done for v2 either; still outstanding.

---

## Environment notes (this machine, not the old container)

- **Windows 11.** `uv` is at `~/.local/bin/uv.exe` and is **not on PATH**; the
  project venv is `backend/.venv` (Python 3.14, uv-managed). Invoke directly:
  `backend/.venv/Scripts/python.exe -m ml.train_v3`.
- **The database is the live Supabase project**, not a local Postgres — the
  connection string is in `backend/.env`. It is populated: 139,029 player-gameweek
  rows, 2026-27 pool of 558 players, 380 fixtures, 0 results yet.
- **`backend/data/raw/` and `backend/ml/artifacts/` are gitignored.** After a
  clean checkout you need, in order: `ml.elo_prob` (fits the Elo→probability map
  the market features need — everything fails with a `FileNotFoundError` on
  `elo_prob_params.json` without it), then `ml.train_v3`, then `ml.predict_v3`.
- Console output is cp1252; non-ASCII player names raise
  `UnicodeEncodeError`. Prefix with `PYTHONIOENCODING=utf-8`.
- Timings on this machine: training frame ~50s, team frame ~10s, one fold ~25s,
  full four-fold training ~7min, `predict_v3` at 4000 draws ~2min.
- The Wikipedia loader is polite and cached; a cold run of
  `--international` fetches 50-odd pages.

## Key design decisions (don't re-litigate without cause)

Carried over from v2 and still true:
- Player/team identity is the stable FPL `code`, never per-season element ids.
- Betting odds calibrate an Elo→probability map (`ml/elo_prob.py`); odds are
  never direct features, because future fixtures have none.
- `player_seasons.status` is a season-end snapshot for historical seasons, so
  availability is an inference-time hard gate and never a training feature.
- FPL 2024-25 "assistant manager" elements (position 5) are excluded everywhere.

New with v3:
- **Points arithmetic is exact, never fitted.** Anything that prices an event
  goes through `ml/scoring.py`, which is validated against every archived row.
- **Rates are per 90 minutes**, via a LightGBM `init_score` Poisson offset. That
  is what makes minutes and scoring separable, so one model covers a cameo and a
  full start instead of needing v2's empirical cameo constant.
- **Training on a rate needs real exposure.** `components/base.MIN_MINUTES = 30`:
  with an offset, a five-minute cameo that produced a goal asserts 18 goals per
  90, and that leverage is noise. Raising the floor cut fold MAE 0.951→0.945.
  Prediction is unfiltered.
- **`ev` is analytic, `ev_mc` is the simulated mean.** They measure the same
  thing and fail differently; see bug 4.
- **A component that cannot be fitted on a fold contributes zero and is flagged**
  (`defcon_available` in the report). The alternative — borrowing the test
  season's data — would leak.
- **The acceptance gate is not tuned to pass.** `--ship-anyway` records an
  override in the artifacts; thresholds are never quietly moved to clear it.

## Git notes

- Branch `develop`, pushed. No PR opened; the user has not asked for one.
- No commit signing is configured on this machine and there are no hooks (the old
  handover's SSH-signing requirement was specific to the previous container).
- `backend/uv.lock` carries a modification that predates this work and is
  deliberately left uncommitted. `.agents/`, `.cursor/` and `skills-lock.json`
  are likewise untouched editor/tool scaffolding.
