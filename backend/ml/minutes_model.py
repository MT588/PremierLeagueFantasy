"""Stage A: 3-class minutes model — P(0 min), P(1-59), P(60+).

Minutes are trimodal and the FPL appearance-point rule steps at 60, so the
class boundaries are exactly the payoff-relevant quantities.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.features import FEATURES_BY_GROUP

MINUTES_FEATURES = [
    *FEATURES_BY_GROUP["meta"],
    "minutes_avg_3",
    "minutes_avg_5",
    "minutes_avg_10",
    "minutes_ewma_hl3",
    "points_avg_5",
    "season_ppg",
    *FEATURES_BY_GROUP["schedule"],
    *FEATURES_BY_GROUP["manager"],
    "minutes_share_prev1",
    "starts_prev1",
    "seasons_in_pl",
    "age_years",
]

PARAMS = {
    "objective": "multiclass",
    "num_class": 3,
    "metric": "multi_logloss",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "verbosity": -1,
}


def minutes_class(minutes: pd.Series) -> np.ndarray:
    """0 = did not play, 1 = cameo (1-59), 2 = started (60+)."""
    return np.select([minutes <= 0, minutes < 60], [0, 1], default=2)


def train(fit: pd.DataFrame, valid: pd.DataFrame) -> lgb.Booster:
    dtrain = lgb.Dataset(
        fit[MINUTES_FEATURES],
        label=minutes_class(fit["minutes"]),
        categorical_feature=["position"],
    )
    dvalid = lgb.Dataset(
        valid[MINUTES_FEATURES], label=minutes_class(valid["minutes"]), reference=dtrain
    )
    model = lgb.train(
        PARAMS,
        dtrain,
        num_boost_round=1500,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    return model


def refit(full: pd.DataFrame, best_iteration: int) -> lgb.Booster:
    dtrain = lgb.Dataset(
        full[MINUTES_FEATURES],
        label=minutes_class(full["minutes"]),
        categorical_feature=["position"],
    )
    return lgb.train(PARAMS, dtrain, num_boost_round=max(best_iteration, 10))


def predict_proba(model: lgb.Booster, df: pd.DataFrame) -> np.ndarray:
    return model.predict(
        df[MINUTES_FEATURES], num_iteration=model.best_iteration or None
    )


def played_last_heuristic(fit: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Baseline: empirical class distribution conditioned on started_last."""
    y_fit = minutes_class(fit["minutes"])
    probs = {}
    for flag in (0.0, 1.0):
        mask = fit["started_last"].fillna(0.0) == flag
        counts = np.bincount(y_fit[mask.to_numpy()], minlength=3).astype(float)
        probs[flag] = counts / counts.sum()
    flags = test["started_last"].fillna(0.0).to_numpy()
    return np.stack([probs[f if f in probs else 0.0] for f in flags])
