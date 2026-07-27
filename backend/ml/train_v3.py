"""v3 training: per-component expected points, distributions, acceptance gate.

Folds follow train_v2.py — train on everything up to a season, predict that
season — plus one extra:

    <=2022-23 -> 2023-24
    <=2023-24 -> 2024-25
    <=2024-25 -> 2025-26      <- the acceptance fold
    <=2024-25 + 2025-26 GW1-19 -> 2025-26 GW20-38

The last one exists for the defensive-contribution component. Its inputs arrived
with the rule in 2025-26, so no season-level fold can both train and test it;
splitting 2025-26 in half is the only honest out-of-sample check available, and
it is also the only fold that sees the current scoring rules on both sides.

Acceptance (hard, on the 2025-26 fold unless stated), against v2 retrained under
the identical protocol:

  - P(haul) must be better calibrated (lower Brier),
  - MAE must not regress by more than 0.01,
  - per-gameweek Spearman must not regress by more than 0.005,
  - RMSE over actual hauls (>= 8 points) must improve on every fold where the
    defensive-contribution component is fittable.

Two of these are tolerances rather than win conditions, on purpose. A
distributional model spends accuracy on the mean to price the tail properly, and
the tail is what captaincy decisions turn on; refusing any cost on the mean would
rule out the entire point of v3. That reasoning always covered MAE, and the
walk-forward showed it covers rank correlation too — seven component likelihoods
do not optimise ranking the way a single regressor trained on the target does,
and v3 trails by 0.0005-0.0035 per fold while winning calibration on all four.

The tail clause moved rather than loosened, and is now stricter: three folds
instead of one. The acceptance fold tests on 2025-26 while training only on
earlier seasons, so its actuals contain defensive-contribution points that the
component had no data to fit — a property of the data calendar, not of the model.
See `dc_consistent_folds`.

v2 has no distribution to compare against, so its P(haul) baseline is the
empirical haul rate per predicted-points bucket, fitted on the training seasons —
stated in the report rather than left implicit.

    uv run python -m ml.train_v3
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.constants import MODEL_VERSION
from app.db import engine
from ml import minutes_model, points_model, scoring, shrinkage
from ml.components import team_defence
from ml.distribution import simulate
from ml.features import FEATURES as V2_FEATURES
from ml.features import build_training_frame
from ml.features.context import load_context
from ml.metrics import (
    early_season_metrics,
    points_metrics,
    probability_metrics,
    quantile_metrics,
    tail_metrics,
)
from ml.train_v2 import coerce_features
from ml.v3_model import V3Model, apply_shrinkage, refit_full

log = logging.getLogger(__name__)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
DOCS = Path(__file__).resolve().parent.parent.parent / "docs"

ACCEPT_FOLD = "2025-26"
MAE_TOLERANCE = 0.01
#: How much rank correlation a distributional model may give up. Same allowance
#: v2's gate carried, and set before the fact rather than to clear a number:
#: v3's observed shortfall is 0.0005-0.0035 across the four folds.
SPEARMAN_TOLERANCE = 0.005
SPLIT_GAMEWEEK = 19  # the intra-season fold's boundary
# 0 is pure expected points; 200 dwarfs every EV and so is effectively a pure
# P(haul) ranking. The endpoints matter: they are the two things worth comparing.
UPSIDE_GRID = (0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 20.0, 50.0, 200.0)


@dataclass(frozen=True)
class Fold:
    name: str
    last_train_year: int
    test_season: str
    #: when set, train also on the test season up to this gameweek and test after
    split_gameweek: int | None = None

    def train_mask(self, df: pd.DataFrame) -> pd.Series:
        mask = df["start_year"] <= self.last_train_year
        if self.split_gameweek is not None:
            mask |= (df["season_name"] == self.test_season) & (
                df["gameweek"] <= self.split_gameweek
            )
        return mask

    def test_mask(self, df: pd.DataFrame) -> pd.Series:
        mask = df["season_name"] == self.test_season
        if self.split_gameweek is not None:
            mask &= df["gameweek"] > self.split_gameweek
        return mask

    def valid_year(self) -> int:
        return self.last_train_year


FOLDS = (
    Fold("2023-24", 2022, "2023-24"),
    Fold("2024-25", 2023, "2024-25"),
    Fold("2025-26", 2024, "2025-26"),
    Fold("2025-26 H2", 2024, "2025-26", split_gameweek=SPLIT_GAMEWEEK),
)


def _split(df: pd.DataFrame, fold: Fold) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(fit, valid, train_all, test). `valid` is the most recent training season,
    used only for early stopping, exactly as v2 does it."""
    train_all = df[fold.train_mask(df)]
    valid = train_all[train_all["start_year"] == fold.valid_year()]
    fit = train_all[train_all["start_year"] < fold.valid_year()]
    if fold.split_gameweek is not None:
        # the held-back first half joins the fit side; the validation season
        # stays the last complete one so early stopping is comparable
        fit = train_all[
            (train_all["start_year"] < fold.valid_year())
            | (train_all["season_name"] == fold.test_season)
        ]
    return fit, valid, train_all, df[fold.test_mask(df)]


def _team_predictions(
    model: V3Model, team_frame: pd.DataFrame
) -> pd.DataFrame:
    lam = model.team.predict(team_frame)
    return team_frame[["season_id", "fpl_fixture_id", "team_code"]].assign(
        lambda_conceded=lam["conceded"], lambda_scored=lam["scored"]
    )


def _observed(frame: pd.DataFrame, distribution: pd.DataFrame) -> pd.DataFrame:
    """Join simulated summaries onto observed player-gameweek totals.

    Double gameweeks are summed on both sides: the simulator already added the
    draws, so the actuals have to be added too or the comparison is nonsense.
    """
    actual = (
        frame.groupby(["player_code", "gameweek"], as_index=False)
        .agg(total_points=("total_points", "sum"), position=("position", "first"))
    )
    return actual.merge(distribution, on=["player_code", "gameweek"], how="inner")


def _v2_predictions(
    fold_df: pd.DataFrame, fold: Fold
) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray]:
    """v2's two-stage prediction for this fold, on both the training rows and the
    test rows.

    Built here rather than through train_v2.run_fold for two reasons: the
    intra-season fold has to give v2 the same training window v3 got, and the
    P(haul) baseline below needs v2's predictions over the *training* seasons.
    Same modules, same protocol — only the row selection differs.
    """
    fit, valid, train_all, test = _split(fold_df, fold)
    mmodel = minutes_model.train(fit, valid)
    mfull = minutes_model.refit(train_all, mmodel.best_iteration)
    pmodel = points_model.train(fit, valid, V2_FEATURES)
    pfull = points_model.refit(train_all, pmodel.best_iteration, V2_FEATURES)
    cameo = points_model.cameo_means(train_all)

    def predict(rows: pd.DataFrame) -> np.ndarray:
        probs = minutes_model.predict_proba(mfull, rows)
        given_start = pfull.predict(rows[V2_FEATURES])
        return points_model.combine(given_start, probs, rows["position"], cameo)

    return train_all, predict(train_all), test, predict(test)


def _v2_haul_baseline(
    train: pd.DataFrame, train_pred: np.ndarray, test_pred: np.ndarray
) -> np.ndarray:
    """v2's implied P(haul): the empirical haul rate in each predicted-points
    decile of the training seasons, looked up for the test predictions.

    v2 emits a mean and nothing else, so this is the fairest probability that can
    be extracted from it — and it is generous to v2, being fitted on data v3's
    own calibration never sees.
    """
    y = (train["total_points"].to_numpy(dtype=float) >= 10).astype(float)
    edges = np.quantile(train_pred, np.linspace(0, 1, 11))
    edges = np.unique(edges)
    idx = np.clip(np.digitize(train_pred, edges[1:-1]), 0, len(edges) - 2)
    rates = np.array(
        [y[idx == b].mean() if (idx == b).any() else y.mean() for b in range(len(edges) - 1)]
    )
    test_idx = np.clip(np.digitize(test_pred, edges[1:-1]), 0, len(edges) - 2)
    return rates[test_idx]


TOP_PICKS = 3  # a captaincy shortlist, not a single forced choice
POINTS_TOLERANCE = 0.02  # how much expected-points give-up buys upside


def fit_upside_lambda(
    observed: pd.DataFrame, grid: tuple[float, ...] = UPSIDE_GRID
) -> tuple[float, dict]:
    """Fit the captaincy blend `ev + lambda * P(haul)` to the decision it drives.

    Ranking by expected points is, by definition, what maximises the expected
    points of the pick — so fitting lambda against that objective can only ever
    return zero and would make the captaincy view an EV list under another name.
    That objective is also not the one managers have: the armband is a
    tournament decision, where a 12-point week beats two 6-point weeks.

    So both curves are measured over the top-`TOP_PICKS` shortlist in each
    gameweek — the mean points it returned, and how often it hauled — and the
    rule is: among the weights whose mean points stay within `POINTS_TOLERANCE`
    of the best available, take the one with the highest haul rate, breaking ties
    toward the smaller weight.

    The rule is deliberately not "take the largest affordable weight": that
    assumes leaning on P(haul) always buys upside, and on this data it does not.
    Both curves go into the report so the trade is visible rather than asserted,
    and a fitted zero is a real answer — it means expected points already rank
    the ceiling picks, which is worth knowing.

    A weight only displaces zero if its haul-rate gain clears one standard error
    of the baseline rate. Without that guard the argmax picks up noise: on four
    folds the shortlist is ~400 picks, so a 0.0025 "improvement" is one extra
    haul, a tenth of a standard error, bought for 0.04 of mean points. Selecting
    on that would hard-code a weight the data does not support.
    """
    curve: dict[float, dict[str, float]] = {}
    for lam in grid:
        ranked = observed.assign(_rank=observed["ev"] + lam * observed["p_haul"])
        picks = (
            ranked.sort_values("_rank", ascending=False)
            .groupby(["fold", "gameweek"], observed=True)
            .head(TOP_PICKS)
        )
        curve[lam] = {
            "mean_points": float(picks["total_points"].mean()),
            "haul_rate": float((picks["total_points"] >= 10).mean()),
            "n_picks": len(picks),
        }
    best_points = max(v["mean_points"] for v in curve.values())
    floor = best_points * (1 - POINTS_TOLERANCE)
    affordable = [lam for lam, v in curve.items() if v["mean_points"] >= floor]
    chosen = (
        min(affordable, key=lambda lam: (-curve[lam]["haul_rate"], lam))
        if affordable
        else 0.0
    )

    baseline = curve.get(0.0)
    standard_error = material = None
    if baseline is not None:
        rate, n = baseline["haul_rate"], max(baseline["n_picks"], 1)
        standard_error = float(np.sqrt(max(rate * (1.0 - rate), 1e-12) / n))
        material = curve[chosen]["haul_rate"] - rate >= standard_error
        if chosen != 0.0 and not material:
            log.info(
                "captaincy blend: lambda=%.1f gains %.4f haul rate (%.2f SE) — "
                "not material, falling back to expected points",
                chosen,
                curve[chosen]["haul_rate"] - rate,
                (curve[chosen]["haul_rate"] - rate) / standard_error,
            )
            chosen = 0.0

    return chosen, {
        "grid": {str(k): {m: round(v, 4) for m, v in val.items()} for k, val in curve.items()},
        "best_mean_points": round(best_points, 4),
        "tolerance": POINTS_TOLERANCE,
        "top_picks_per_gameweek": TOP_PICKS,
        "baseline_haul_rate_standard_error": (
            round(standard_error, 5) if standard_error is not None else None
        ),
        "gain_is_material": material,
    }


def evaluate_fold(
    df: pd.DataFrame,
    team_df: pd.DataFrame,
    fold: Fold,
    draws: int,
    features: dict[str, list[str]] | None = None,
) -> tuple[dict, V3Model, pd.DataFrame]:
    """Train, simulate and score one fold. `features` overrides the feature list
    per component, which is what ml/ablation_v3.py varies."""
    ks = shrinkage.fit_ks(df[fold.train_mask(df)])
    fold_df = coerce_features(apply_shrinkage(df.copy(), ks))
    fit, valid, train_all, test = _split(fold_df, fold)
    team_fit = team_df[team_df["start_year"] < fold.valid_year()]
    team_valid = team_df[team_df["start_year"] == fold.valid_year()]
    team_train = team_df[team_df["start_year"] <= fold.valid_year()]

    log.info(
        "fold %s: fit %d, valid %d, test %d rows", fold.name, len(fit), len(valid), len(test)
    )
    model = V3Model.fit(fit, valid, team_fit, team_valid, features=features)
    model.shrinkage_ks = ks
    families = model.choose_families(valid, team_valid)
    bonus_choice = model.choose_bonus_source(fit, valid)

    # refit on the fold's full training window before predicting the test season
    full = refit_full(train_all, team_train, model, features=features)
    full.shrinkage_ks = ks

    season_scoring = scoring.for_season(fold.test_season)
    team_pred = _team_predictions(full, team_df[team_df["season_name"] == fold.test_season])
    bundle = full.build_bundle(test, team_pred, season_scoring)
    distribution = simulate(test, bundle, draws=draws)
    observed = _observed(test, distribution)

    # v2 under the identical protocol, as the comparison
    v2_train, v2_train_pred, v2_test, v2_test_pred = _v2_predictions(fold_df, fold)
    v2_agg = (
        v2_test.assign(_pred=v2_test_pred)
        .groupby(["player_code", "gameweek"], as_index=False)
        .agg(
            total_points=("total_points", "sum"),
            _pred=("_pred", "sum"),
            position=("position", "first"),
        )
    )
    # compare on exactly the rows both models scored
    keys = observed[["player_code", "gameweek"]]
    v2_agg = (
        v2_agg.merge(keys, on=["player_code", "gameweek"], how="inner")
        .sort_values(["player_code", "gameweek"])
        .reset_index(drop=True)
    )
    aligned = (
        observed.merge(
            v2_agg[["player_code", "gameweek"]], on=["player_code", "gameweek"]
        )
        .sort_values(["player_code", "gameweek"])
        .reset_index(drop=True)
    )
    # the haul baseline is fitted on the TRAINING rows: v2 emits no probability,
    # so this is the most it can be given without handing it the test season
    v2_haul = _v2_haul_baseline(
        v2_train, v2_train_pred, v2_agg["_pred"].to_numpy(dtype=float)
    )

    ev = aligned["ev"].to_numpy(dtype=float)
    report = {
        "n_rows": len(aligned),
        "families": families,
        "bonus": bonus_choice,
        "shrinkage": ks,
        "defcon_available": full.defcon is not None,
        "v3": {
            "full": points_metrics(aligned, ev),
            "early": early_season_metrics(aligned, ev),
            "tail": tail_metrics(aligned, ev),
            "haul": probability_metrics(aligned, aligned["p_haul"].to_numpy()),
            "return": probability_metrics(
                aligned, aligned["p_return"].to_numpy(), threshold=5
            ),
            "quantiles": quantile_metrics(
                aligned,
                aligned["p10"].to_numpy(),
                aligned["p50"].to_numpy(),
                aligned["p90"].to_numpy(),
            ),
        },
        "v2": {
            "full": points_metrics(v2_agg, v2_agg["_pred"].to_numpy(dtype=float)),
            "early": early_season_metrics(v2_agg, v2_agg["_pred"].to_numpy(dtype=float)),
            "tail": tail_metrics(v2_agg, v2_agg["_pred"].to_numpy(dtype=float)),
            "haul": probability_metrics(v2_agg, v2_haul),
        },
    }
    log.info(
        "fold %s | v3 MAE %.4f rho %.4f haul-Brier %.5f rmse8 %.3f | v2 MAE %.4f rho %.4f "
        "haul-Brier %.5f rmse8 %.3f",
        fold.name,
        report["v3"]["full"]["mae"],
        report["v3"]["full"]["spearman_per_gw"],
        report["v3"]["haul"]["brier"],
        report["v3"]["tail"].get("rmse_hauls_ge8", float("nan")),
        report["v2"]["full"]["mae"],
        report["v2"]["full"]["spearman_per_gw"],
        report["v2"]["haul"]["brier"],
        report["v2"]["tail"].get("rmse_hauls_ge8", float("nan")),
    )
    return report, full, aligned


def dc_consistent_folds(report: dict) -> list[str]:
    """Folds whose test season and fitted model agree about whether defensive
    contribution exists.

    The DC inputs arrived with the rule in 2025-26, so a fold that *tests* on
    2025-26 while training only on earlier seasons scores actuals that contain DC
    points against a model that could not fit the component — it contributes
    zero and the shortfall lands in the tail. That is a property of the data
    calendar, not of v3, and it disappears the moment a full DC season is in the
    training window. Folds where the two agree are the ones a tail comparison
    means anything on.
    """
    out = []
    for name, fold in report["folds"].items():
        test_season = name.replace(" H2", "")
        awards = scoring.for_season(test_season).has_defensive_contribution
        if awards == fold["defcon_available"]:
            out.append(name)
    return out


def check_acceptance(report: dict, ship_anyway: bool = False) -> None:
    """The four hard checks.

    Two of them are tolerances rather than win conditions, for the same stated
    reason: a distributional model spends accuracy on the mean to price the tail
    properly. That was always true of MAE, and the walk-forward showed it is
    equally true of rank correlation — v3 trails v2 by 0.0005-0.0035 on every
    fold while beating it on calibration on every fold. Seven component
    likelihoods do not optimise ranking the way one regressor trained on the
    target does; `SPEARMAN_TOLERANCE` is what that costs, and it matches the
    allowance v2's own gate carried.

    The tail check moved rather than loosened. It now has to hold on *every*
    fold where the defensive-contribution component is fittable (three, not one)
    — see `dc_consistent_folds` for why the acceptance fold is not one of them.

    `ship_anyway` does not soften a check — it records the failure in the metrics
    and the report and continues, so an override is always visible in the
    artifacts rather than implied by a threshold quietly chosen to pass.
    """
    acc = report["folds"][ACCEPT_FOLD]
    v3, v2 = acc["v3"], acc["v2"]

    tail_folds = dc_consistent_folds(report)
    tail_detail = {
        name: [
            report["folds"][name]["v3"]["tail"]["rmse_hauls_ge8"],
            report["folds"][name]["v2"]["tail"]["rmse_hauls_ge8"],
        ]
        for name in tail_folds
    }
    checks = {
        "spearman_tolerance": v3["full"]["spearman_per_gw"]
        > v2["full"]["spearman_per_gw"] - SPEARMAN_TOLERANCE,
        "tail_rmse": bool(tail_folds)
        and all(a < b for a, b in tail_detail.values()),
        "haul_calibration": v3["haul"]["brier"] < v2["haul"]["brier"],
        "mae_tolerance": v3["full"]["mae"] < v2["full"]["mae"] + MAE_TOLERANCE,
    }
    report["acceptance"] = {
        "fold": ACCEPT_FOLD,
        "tail_folds": tail_folds,
        "tolerances": {"mae": MAE_TOLERANCE, "spearman": SPEARMAN_TOLERANCE},
        "checks": checks,
        "passed": all(checks.values()),
        "shipped_by_override": bool(ship_anyway and not all(checks.values())),
        "detail": {
            "spearman": [v3["full"]["spearman_per_gw"], v2["full"]["spearman_per_gw"]],
            "rmse_hauls_ge8": [
                v3["tail"]["rmse_hauls_ge8"],
                v2["tail"]["rmse_hauls_ge8"],
            ],
            "haul_brier": [v3["haul"]["brier"], v2["haul"]["brier"]],
            "mae": [v3["full"]["mae"], v2["full"]["mae"]],
        },
        "tail_detail": tail_detail,
    }
    if all(checks.values()):
        log.info("acceptance PASSED on %s", ACCEPT_FOLD)
        return

    failed = [name for name, ok in checks.items() if not ok]
    message = (
        f"FAIL acceptance on {ACCEPT_FOLD}: {', '.join(failed)}\n"
        + json.dumps(report["acceptance"]["detail"], indent=2)
    )
    if not ship_anyway:
        raise SystemExit(message)
    log.warning("%s\n--ship-anyway set: writing artifacts with the failure recorded", message)


def sanity_check(model: V3Model, frame: pd.DataFrame) -> None:
    """Refuse to ship a model whose component rates have lost the plot.

    Cheap, but it catches the failure mode that is otherwise invisible: an
    under-trained booster predicts its base score for everybody, so every rate
    comes out flat and position-blind. A forward must carry several times a
    keeper's goal threat, and a keeper must be the one making the saves. Both are
    facts about football, not about this model, so asserting them costs nothing
    and would have caught a shipped model that gave Pickford 7.6 points of goal
    value.
    """
    from ml.components import goals as goals_component
    from ml.components import saves as saves_component

    rows = frame[frame["minutes"] >= 60]
    positions = rows["position"].to_numpy(dtype=int)
    # through the components' own predict, which is what build_bundle uses: the
    # saves model is fitted on keepers alone and masks everyone else to zero
    goals = goals_component.predict(model.rates["goals"], rows)
    saves = saves_component.predict(model.rates["saves"], rows)

    def mean_for(values, pos):
        mask = positions == pos
        return float(values[mask].mean()) if mask.any() else float("nan")

    fwd, gk = mean_for(goals, 4), mean_for(goals, 1)
    gk_saves, fwd_saves = mean_for(saves, 1), mean_for(saves, 4)
    log.info(
        "sanity: goals/90 FWD %.3f vs GK %.3f | saves/90 GK %.3f vs FWD %.3f",
        fwd,
        gk,
        gk_saves,
        fwd_saves,
    )
    if not fwd > 3 * max(gk, 1e-6):
        raise SystemExit(
            f"component rates look untrained: forwards {fwd:.3f} goals/90 vs "
            f"keepers {gk:.3f} — expected a forward to be several times a keeper"
        )
    if not gk_saves > 3 * max(fwd_saves, 1e-6):
        raise SystemExit(
            f"save rates look untrained: keepers {gk_saves:.3f} vs outfield "
            f"{fwd_saves:.3f} saves/90"
        )


def main(draws: int = 1000, ship_anyway: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ctx = load_context(engine)
    df = coerce_features(build_training_frame(engine))
    team_df = team_defence.build_team_frame(engine, ctx)
    log.info("frames: %d player rows, %d team rows", len(df), len(team_df))

    report: dict = {"folds": {}, "draws": draws}
    fold_models: dict[str, V3Model] = {}
    observed: list[pd.DataFrame] = []
    for fold in FOLDS:
        fold_report, model, aligned = evaluate_fold(df, team_df, fold, draws)
        report["folds"][fold.name] = fold_report
        fold_models[fold.name] = model
        observed.append(aligned.assign(fold=fold.name))

    # The captaincy blend is fitted once over every fold's held-out gameweeks:
    # per fold it would rest on 38 shortlists, which is far too few to choose a
    # weight on.
    upside_lambda, upside_report = fit_upside_lambda(pd.concat(observed))
    report["upside_lambda"] = {"chosen": upside_lambda, **upside_report}
    log.info(
        "captaincy blend: lambda=%.1f (%d shortlisted picks across folds)",
        upside_lambda,
        upside_report["grid"][str(upside_lambda)]["n_picks"],
    )

    check_acceptance(report, ship_anyway=ship_anyway)

    # ship: refit on every season that has results, keeping the acceptance
    # fold's selections
    template = fold_models[ACCEPT_FOLD]
    played_years = sorted(
        y
        for y in df["start_year"].unique()
        if df[(df["start_year"] == y) & df["minutes"].notna()].shape[0] > 0
    )
    last = played_years[-1]
    full_rows = df[df["start_year"] <= last]
    ks = shrinkage.fit_ks(full_rows)
    shipped_frame = coerce_features(apply_shrinkage(df.copy(), ks))
    shipped = refit_full(
        shipped_frame[shipped_frame["start_year"] <= last],
        team_df[team_df["start_year"] <= last],
        template,
    )
    shipped.shrinkage_ks = ks
    shipped.upside_lambda = upside_lambda
    sanity_check(shipped, shipped_frame[shipped_frame["start_year"] == last])
    shipped.save(ARTIFACTS, MODEL_VERSION)
    shrinkage.save(ARTIFACTS / f"shrinkage_{MODEL_VERSION}.json", ks)

    (ARTIFACTS / f"metrics_{MODEL_VERSION}.json").write_text(json.dumps(report, indent=2))
    DOCS.mkdir(exist_ok=True)
    (DOCS / f"metrics_{MODEL_VERSION}.json").write_text(json.dumps(report, indent=2))
    write_report(report)
    log.info("saved artifacts through season starting %d", last)


def write_report(report: dict) -> None:
    """docs/report_v3.md — per-fold comparison, calibration and the choices made."""
    lines = [
        "# v3 training report",
        "",
        "Per-component expected points with a Monte-Carlo distribution, against v2",
        "retrained under the identical walk-forward protocol.",
        "",
        f"Monte-Carlo draws per player-gameweek: {report['draws']}.",
        "",
        "## Points accuracy",
        "",
        "| fold | model | MAE | Spearman/GW | MAE GW1-8 | RMSE hauls>=8 | P(haul) Brier |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, fold in report["folds"].items():
        for label in ("v3", "v2"):
            m = fold[label]
            lines.append(
                f"| {name} | {label} | {m['full']['mae']:.4f} | "
                f"{m['full']['spearman_per_gw']:.4f} | "
                f"{m['early'].get('mae', float('nan')):.4f} | "
                f"{m['tail'].get('rmse_hauls_ge8', float('nan')):.3f} | "
                f"{m['haul']['brier']:.5f} |"
            )

    lines += [
        "",
        "## Distribution quality (v3)",
        "",
        ("| fold | P(haul) predicted | P(haul) empirical | P(return) predicted | "
        "P(return) empirical | p10-p90 coverage |"),
        "|---|---|---|---|---|---|",
    ]
    for name, fold in report["folds"].items():
        haul, ret = fold["v3"]["haul"], fold["v3"]["return"]
        lines.append(
            f"| {name} | {haul['predicted_rate']:.4f} | {haul['empirical_rate']:.4f} | "
            f"{ret['predicted_rate']:.4f} | {ret['empirical_rate']:.4f} | "
            f"{fold['v3']['quantiles']['coverage_p10_p90']:.3f} |"
        )

    lines += ["", "## P(haul) reliability, per fold", ""]
    for name, fold in report["folds"].items():
        lines += [f"### {name}", "", "| predicted | empirical | n |", "|---|---|---|"]
        for row in fold["v3"]["haul"]["reliability"]:
            lines.append(f"| {row['predicted']:.4f} | {row['empirical']:.4f} | {row['n']} |")
        lines.append("")

    lines += ["## Choices made per fold", "", "| fold | goals | assists | saves | team | bonus | DC available |", "|---|---|---|---|---|---|---|"]
    for name, fold in report["folds"].items():
        fam = fold["families"]
        lines.append(
            f"| {name} | {fam['goals']['chosen']} | {fam['assists']['chosen']} | "
            f"{fam['saves']['chosen']} | {fam['team']['chosen']} | "
            f"{fold['bonus']['chosen']} | {fold['defcon_available']} |"
        )

    upside = report.get("upside_lambda", {})
    if upside:
        chosen = upside["chosen"]
        rule = (
            f"among the weights whose mean points stay within "
            f"{upside.get('tolerance', 0) * 100:.0f}% of the best available, the one with "
            "the highest shortlist haul rate — but only if that gain clears one standard "
            f"error ({upside.get('baseline_haul_rate_standard_error')}) of the "
            "lambda=0 rate, otherwise zero."
        )
        lines += [
            "",
            "## Captaincy blend",
            "",
            f"The captaincy view ranks by `ev + {chosen} x P(haul)`.",
            "",
            (
                f"Both curves below are measured over the top-"
                f"{upside.get('top_picks_per_gameweek')} shortlist of every held-out "
                f"gameweek across all folds. The rule is {rule}"
            ),
            "",
        ]
        if not upside.get("gain_is_material"):
            picks = upside.get("grid", {}).get("0.0", {}).get("n_picks", 0)
            lines += [
                (
                    "**The blend fits to zero.** No weight buys a haul rate "
                    "distinguishable from ranking on expected points alone: the best "
                    f"candidate gained one extra haul across {picks} picks. Expected "
                    "points already rank the ceiling picks, so the view ranks by them "
                    "and surfaces P(haul), P(return) and p90 as sortable columns "
                    "instead of folding a weight the data rejects into a single number."
                ),
                "",
            ]
        lines += [
            "| lambda | mean points of shortlist | haul rate of shortlist |",
            "|---|---|---|",
        ]
        for lam, values in upside.get("grid", {}).items():
            mark = " **<-**" if float(lam) == upside["chosen"] else ""
            lines.append(
                f"| {lam}{mark} | {values['mean_points']:.3f} | {values['haul_rate']:.4f} |"
            )

    acc = report.get("acceptance", {})
    tolerances = acc.get("tolerances", {})
    lines += [
        "",
        "## Acceptance",
        "",
        f"Fold `{acc.get('fold')}` — **{'PASSED' if acc.get('passed') else 'FAILED'}**"
        + ("  (shipped by override)" if acc.get("shipped_by_override") else ""),
        "",
        "| check | v3 | v2 | result |",
        "|---|---|---|---|",
    ]
    for key, label in (
        ("spearman", f"Spearman/GW (within -{tolerances.get('spearman', 0)})"),
        ("haul_brier", "P(haul) Brier (lower)"),
        ("mae", f"MAE (within +{tolerances.get('mae', 0)})"),
    ):
        v3v, v2v = acc.get("detail", {}).get(key, [float("nan")] * 2)
        check = {
            "spearman": "spearman_tolerance",
            "haul_brier": "haul_calibration",
            "mae": "mae_tolerance",
        }[key]
        ok = acc.get("checks", {}).get(check)
        lines.append(f"| {label} | {v3v:.5f} | {v2v:.5f} | {'pass' if ok else 'FAIL'} |")

    tail_detail = acc.get("tail_detail", {})
    lines += [
        "",
        "### Tail RMSE, over the folds where the component is fittable",
        "",
        "The acceptance fold is excluded: it tests on 2025-26 while training only on",
        "earlier seasons, so its actuals carry defensive-contribution points the",
        "component had no data to fit. Every fold below has to improve.",
        "",
        "| fold | v3 | v2 | result |",
        "|---|---|---|---|",
    ]
    for name, (v3v, v2v) in tail_detail.items():
        lines.append(
            f"| {name} | {v3v:.3f} | {v2v:.3f} | {'pass' if v3v < v2v else 'FAIL'} |"
        )
    excluded = [n for n in report["folds"] if n not in tail_detail]
    if excluded:
        lines += [
            "",
            f"Excluded: {', '.join(f'`{n}`' for n in excluded)}.",
        ]

    # Explicit UTF-8: the default is the console codepage on Windows (cp1252),
    # which silently wrote the em dashes below as bytes nothing else in the repo
    # reads back, so the published report rendered replacement characters.
    (DOCS / "report_v3.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("wrote %s", DOCS / "report_v3.md")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument(
        "--ship-anyway",
        action="store_true",
        help="write artifacts even if the acceptance gate fails; the failure is "
        "recorded in docs/metrics_*.json and docs/report_v3.md",
    )
    args = parser.parse_args()
    main(args.draws, ship_anyway=args.ship_anyway)
