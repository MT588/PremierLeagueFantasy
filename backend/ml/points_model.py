"""Stage B: points-given-start regressor + the two-stage combination."""

import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.features import FEATURES

PARAMS = {
    # L2 -> conditional mean: expected points sum correctly across a squad
    "objective": "regression",
    "metric": "mae",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "verbosity": -1,
}


def train(
    fit: pd.DataFrame, valid: pd.DataFrame, features: list[str] | None = None
) -> lgb.Booster:
    features = features or FEATURES
    fit_started = fit[fit["minutes"] >= 60]
    valid_started = valid[valid["minutes"] >= 60]
    dtrain = lgb.Dataset(
        fit_started[features],
        label=fit_started["total_points"],
        categorical_feature=["position"] if "position" in features else [],
    )
    dvalid = lgb.Dataset(
        valid_started[features], label=valid_started["total_points"], reference=dtrain
    )
    return lgb.train(
        PARAMS,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )


def refit(
    full: pd.DataFrame, best_iteration: int, features: list[str] | None = None
) -> lgb.Booster:
    features = features or FEATURES
    started = full[full["minutes"] >= 60]
    dtrain = lgb.Dataset(
        started[features],
        label=started["total_points"],
        categorical_feature=["position"] if "position" in features else [],
    )
    return lgb.train(PARAMS, dtrain, num_boost_round=max(best_iteration, 10))


def cameo_means(fit: pd.DataFrame) -> dict[int, float]:
    cameo = fit[(fit["minutes"] > 0) & (fit["minutes"] < 60)]
    means = cameo.groupby("position")["total_points"].mean()
    return {int(k): round(float(v), 3) for k, v in means.items()}


def combine(
    points_pred: np.ndarray,
    minutes_probs: np.ndarray,
    positions: pd.Series,
    cameo: dict[int, float],
) -> np.ndarray:
    cameo_vec = positions.map(lambda p: cameo.get(int(p), 1.0)).to_numpy(dtype=float)
    return minutes_probs[:, 2] * points_pred + minutes_probs[:, 1] * cameo_vec


def save_cameo(path, cameo: dict[int, float]) -> None:
    path.write_text(json.dumps(cameo, indent=2))


def load_cameo(path) -> dict[int, float]:
    return {int(k): v for k, v in json.loads(path.read_text()).items()}
