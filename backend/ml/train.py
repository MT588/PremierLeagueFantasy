"""Train the LightGBM points model with a temporal backtest.

Split: train 2021-22..2023-24, validate 2024-25 (early stopping),
test 2025-26 (held out). Must beat the last-5-average baseline.
"""

import json
import logging
from pathlib import Path

import lightgbm as lgb

from app.db import engine
from ml.evaluate import evaluation_report
from ml.features_v1 import FEATURES, TARGET, build_training_frame

log = logging.getLogger(__name__)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
MODEL_VERSION = "lgbm-v1"

TRAIN_SEASONS = ["2021-22", "2022-23", "2023-24"]
VALID_SEASON = "2024-25"
TEST_SEASON = "2025-26"

PARAMS = {
    # L2 predicts the conditional mean: expected points sum correctly across a
    # squad and don't systematically understate high-variance premium players
    # the way an L1/median objective does.
    "objective": "regression",
    "metric": "mae",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "verbosity": -1,
}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    df = build_training_frame(engine)
    log.info("training frame: %d rows", len(df))

    train = df[df["season_name"].isin(TRAIN_SEASONS)]
    valid = df[df["season_name"] == VALID_SEASON]
    test = df[df["season_name"] == TEST_SEASON]
    log.info("split: train=%d valid=%d test=%d", len(train), len(valid), len(test))

    dtrain = lgb.Dataset(
        train[FEATURES], label=train[TARGET], categorical_feature=["position"]
    )
    dvalid = lgb.Dataset(valid[FEATURES], label=valid[TARGET], reference=dtrain)

    model = lgb.train(
        PARAMS,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(200)],
    )
    log.info("best iteration: %d", model.best_iteration)

    report = evaluation_report(model, test)
    print(json.dumps(report, indent=2))

    ARTIFACTS.mkdir(exist_ok=True)
    model.save_model(str(ARTIFACTS / f"model_{MODEL_VERSION}.txt"))
    (ARTIFACTS / f"metrics_{MODEL_VERSION}.json").write_text(
        json.dumps(report, indent=2)
    )
    log.info("saved model + metrics to %s", ARTIFACTS)

    if report["model"]["mae"] >= report["baseline_last5"]["mae"]:
        raise SystemExit("FAIL: model does not beat the last-5-average baseline")
    log.info(
        "OK: model MAE %.4f beats baseline %.4f",
        report["model"]["mae"],
        report["baseline_last5"]["mae"],
    )


if __name__ == "__main__":
    main()
