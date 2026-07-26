"""Assists: the same rate family as goals, over creation rather than shooting.

Kept as its own module rather than folded into a shared "goal involvements"
model because the two are priced differently (a defender's goal is worth six
points, his assist three) and driven by different features — xA, key passes and
set-piece duty rather than npxG.
"""

import numpy as np
import pandas as pd

from ml.components.base import CountModel, refit_rate, train_rate
from ml.features import FEATURES_V3

NAME = "assists"
LABEL = "assists"

FEATURES = list(FEATURES_V3)


def train(fit: pd.DataFrame, valid: pd.DataFrame, features: list[str] | None = None):
    return train_rate(fit, valid, features or FEATURES, LABEL)


def refit(
    full: pd.DataFrame,
    best_iteration: int,
    features: list[str] | None = None,
    alpha: dict[int, float] | None = None,
    family: str = "poisson",
):
    return refit_rate(
        full, best_iteration, features or FEATURES, LABEL, alpha=alpha, family=family
    )


def predict(model: CountModel, df: pd.DataFrame) -> np.ndarray:
    """Assists per 90 minutes."""
    return model.rate(df)
