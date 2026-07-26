"""Phase-A gate: does sample-size-aware form actually help early in a season?

The form-shrinkage and tournament groups are evaluated on the *unchanged* v2
two-stage architecture, so this measures the features and nothing else. The
claim being tested is narrow and falsifiable: naive `rolling(5)` windows are
unrepresentative in the opening weeks, so the blended features should win on
gameweeks 1-8 without costing anything over the full season.

Shrinkage weights are refitted per fold on that fold's training seasons only —
never on the test season — which is why the frame is rebuilt-in-place with
`form_eb.apply` rather than carrying one global `k`.

    uv run python -m ml.eval_form_fix

Writes docs/form_fix_v3.json.
"""

import json
import logging
from pathlib import Path

import pandas as pd

from app.db import engine
from ml import minutes_model, shrinkage
from ml.features import FEATURES, FEATURES_BY_GROUP, build_training_frame, form_eb
from ml.metrics import (
    early_season_metrics,
    multiclass_log_loss,
    points_metrics,
    tail_metrics,
)
from ml.train_v2 import FOLDS, coerce_features, run_fold

log = logging.getLogger(__name__)

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"

CONFIGS: dict[str, list[str]] = {
    "v2 baseline": FEATURES,
    "+ form_eb": FEATURES + FEATURES_BY_GROUP["form_eb"],
    "+ form_eb + tournament": (
        FEATURES + FEATURES_BY_GROUP["form_eb"] + FEATURES_BY_GROUP["tournament"]
    ),
}


def minutes_stage_check(
    df: pd.DataFrame, last_train_year: int, test_season: str
) -> dict:
    """Does the tournament group belong in the *minutes* model rather than the
    points model? A deep summer run plausibly changes whether a player starts,
    not how he scores once he does, so this trains the minutes classifier with
    and without the group and compares log loss — overall and over GW1-8, where
    any tournament effect must live.
    """
    fit = df[df["start_year"] < last_train_year]
    valid = df[df["start_year"] == last_train_year]
    full = df[df["start_year"] <= last_train_year]
    test = df[df["season_name"] == test_season]
    early = test["gameweek"] <= 8
    y = minutes_model.minutes_class(test["minutes"])

    out: dict[str, dict] = {}
    base = list(minutes_model.MINUTES_FEATURES)
    for label, features in (
        ("minutes baseline", base),
        ("minutes + tournament", base + FEATURES_BY_GROUP["tournament"]),
    ):
        model = minutes_model.train(fit, valid, features=features)
        model_full = minutes_model.refit(full, model.best_iteration, features=features)
        probs = minutes_model.predict_proba(model_full, test, features=features)
        out[label] = {
            "logloss": multiclass_log_loss(y, probs),
            "logloss_gw1_8": multiclass_log_loss(
                y[early.to_numpy()], probs[early.to_numpy()]
            ),
            "mean_p_start_gw1_8": float(probs[early.to_numpy(), 2].mean()),
        }
        log.info(
            "%s | %-22s logloss %.5f | GW1-8 %.5f",
            test_season,
            label,
            out[label]["logloss"],
            out[label]["logloss_gw1_8"],
        )
    return out


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    df = coerce_features(build_training_frame(engine))
    log.info("frame: %d rows", len(df))

    report: dict = {"folds": {}, "shrinkage": {}}
    for last_train_year, test_season in FOLDS:
        # fit k on training seasons only, then rebuild the blended columns
        train = df[df["start_year"] <= last_train_year]
        ks = shrinkage.fit_ks(train)
        report["shrinkage"][test_season] = ks
        fold_df = coerce_features(form_eb.apply(df.copy(), ks))
        test = fold_df[fold_df["season_name"] == test_season]

        fold: dict = {}
        for label, features in CONFIGS.items():
            preds, _ = run_fold(fold_df, last_train_year, test_season, features=features)
            fold[label] = {
                "full": points_metrics(test, preds),
                "early": early_season_metrics(test, preds),
                "tail": tail_metrics(test, preds),
            }
            log.info(
                "%s | %-24s full MAE %.4f rho %.4f | GW1-8 MAE %.4f rho %.4f",
                test_season,
                label,
                fold[label]["full"]["mae"],
                fold[label]["full"]["spearman_per_gw"],
                fold[label]["early"].get("mae", float("nan")),
                fold[label]["early"].get("spearman_per_gw", float("nan")),
            )
        fold["minutes stage"] = minutes_stage_check(
            fold_df, last_train_year, test_season
        )
        report["folds"][test_season] = fold

    DOCS.mkdir(exist_ok=True)
    (DOCS / "form_fix_v3.json").write_text(json.dumps(report, indent=2))

    rows = []
    for season, fold in report["folds"].items():
        for label, m in fold.items():
            if label == "minutes stage":
                continue
            rows.append(
                {
                    "fold": season,
                    "config": label,
                    "mae": m["full"]["mae"],
                    "rho": m["full"]["spearman_per_gw"],
                    "mae_gw1_8": m["early"].get("mae"),
                    "rho_gw1_8": m["early"].get("spearman_per_gw"),
                }
            )
    table = pd.DataFrame(rows)
    print("\n" + table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    log.info("wrote %s", DOCS / "form_fix_v3.json")


if __name__ == "__main__":
    main()
