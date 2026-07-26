"""Saves: a keeper's per-90 rate, driven by the shots he is about to face.

FPL pays a point per three saves, which is a step function — so the mean is not
enough and the simulator needs the whole count. The signal is the volume of
shots coming at him, and the frame already measures that from two directions:
`expected_goals_conceded` recorded against his own team (rolled up in
`eb_saves90` and the team model's `own_xgc_6`) and the opponent's attacking
output. A keeper in a bad team facing a good one is the high-saves case, which
is why this component wants the opponent features the v2 points model dropped.

Only keepers are trained on: outfield saves are vanishingly rare and would
otherwise dominate the loss with zeros.
"""

import numpy as np
import pandas as pd

from ml.components.base import CountModel, refit_rate, resolve_features, train_rate
from ml.features import FEATURES_V3
from ml.features.form_eb import SAVES_FEATURES

NAME = "saves"
LABEL = "saves"
POSITIONS = (1,)  # goalkeepers

EXTRAS = list(SAVES_FEATURES)
FEATURES = list(FEATURES_V3) + EXTRAS


def train(fit: pd.DataFrame, valid: pd.DataFrame, features: list[str] | None = None):
    # Far fewer rows than the outfield components (one keeper per team per
    # match), so the leaf minimum has to come down or nothing splits.
    return train_rate(
        fit,
        valid,
        resolve_features(features, FEATURES_V3, EXTRAS),
        LABEL,
        positions=POSITIONS,
        params={"min_data_in_leaf": 40, "num_leaves": 15},
    )


def refit(
    full: pd.DataFrame,
    best_iteration: int,
    features: list[str] | None = None,
    alpha: dict[int, float] | None = None,
    family: str = "poisson",
):
    return refit_rate(
        full,
        best_iteration,
        resolve_features(features, FEATURES_V3, EXTRAS),
        LABEL,
        positions=POSITIONS,
        alpha=alpha,
        family=family,
        params={"min_data_in_leaf": 40, "num_leaves": 15},
    )


def predict(model: CountModel, df: pd.DataFrame) -> np.ndarray:
    """Saves per 90 minutes; zero for outfield players."""
    rate = model.rate(df)
    return np.where(df["position"].to_numpy(dtype=int) == 1, rate, 0.0)
