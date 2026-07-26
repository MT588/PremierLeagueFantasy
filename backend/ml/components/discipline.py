"""Cards: a small negative term, and the suspension context around it.

Worth about -0.15 points a match on average, so this will never move a ranking
on its own. It earns its place in two narrower places: separating two otherwise
identical defenders when one of them is a habitual booking, and flagging the
player sitting on four yellows — who is both more likely to be rested and more
likely to play carefully, which `suspension_gap` exposes to the minutes model.

Red cards are too rare (about one in 250 appearances) to model per player
without overfitting, so they use a per-position base rate measured on the
training rows.
"""

import logging
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.components.base import (
    BINARY_PARAMS,
    NUM_BOOST_ROUND,
    played,
    resolve_features,
    train_binary,
)
from ml.features import FEATURES_V3
from ml.features.form_eb import DISCIPLINE_FEATURES

log = logging.getLogger(__name__)

NAME = "discipline"
EXTRAS = list(DISCIPLINE_FEATURES)
FEATURES = list(FEATURES_V3) + EXTRAS


@dataclass
class DisciplineModel:
    yellow: lgb.Booster
    best_iteration: int
    red_rate: dict[int, float] = field(default_factory=dict)

    def red_for(self, position: np.ndarray) -> np.ndarray:
        lut = np.zeros(5)
        for pos, rate in self.red_rate.items():
            lut[pos] = rate
        return lut[np.asarray(position, dtype=int)]


def train(
    fit: pd.DataFrame, valid: pd.DataFrame, features: list[str] | None = None
) -> DisciplineModel:
    features = resolve_features(features, FEATURES_V3, EXTRAS)
    fit_rows, valid_rows = played(fit), played(valid)
    booster = train_binary(
        fit_rows,
        valid_rows,
        features,
        (fit_rows["yellow_cards"].fillna(0) > 0).astype(float),
        (valid_rows["yellow_cards"].fillna(0) > 0).astype(float),
    )
    return DisciplineModel(
        booster,
        booster.best_iteration or NUM_BOOST_ROUND,
        red_rate=_red_rates(fit_rows),
    )


def refit(
    full: pd.DataFrame, best_iteration: int, features: list[str] | None = None
) -> DisciplineModel:
    features = resolve_features(features, FEATURES_V3, EXTRAS)
    rows = played(full)
    dtrain = lgb.Dataset(
        rows[features],
        label=(rows["yellow_cards"].fillna(0) > 0).astype(float),
        categorical_feature=["position"] if "position" in features else [],
    )
    booster = lgb.train(
        BINARY_PARAMS, dtrain, num_boost_round=max(best_iteration, 10)
    )
    return DisciplineModel(booster, 0, red_rate=_red_rates(rows))


def _red_rates(frame: pd.DataFrame) -> dict[int, float]:
    reds = (frame["red_cards"].fillna(0) > 0).astype(float)
    return {
        int(pos): float(g.mean())
        for pos, g in reds.groupby(frame["position"].to_numpy(dtype=int))
    }


def predict(model: DisciplineModel, df: pd.DataFrame) -> dict[str, np.ndarray]:
    """P(booked) and P(sent off) for a full appearance."""
    yellow = np.clip(
        model.yellow.predict(
            df[model.yellow.feature_name()],
            num_iteration=model.best_iteration or None,
        ),
        0.0,
        1.0,
    )
    return {
        "yellow": np.asarray(yellow, dtype=float),
        "red": model.red_for(df["position"].to_numpy(dtype=int)),
    }
