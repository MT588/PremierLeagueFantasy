"""Goals: a per-90 rate model, Poisson or negative binomial.

Shot quality is the signal that matters and it is already in the frame — the
Understat npxG rates and the shrunk `eb_xg90` / `eb_goals90` blends carry it.
Modelling the rate rather than the points means a defender's six-point goal and
a forward's four-point goal come out of the same model and get priced by
ml/scoring.py, so a rule change costs nothing to absorb.
"""

import numpy as np
import pandas as pd

from ml.components.base import CountModel, refit_rate, train_rate
from ml.features import FEATURES_V3

NAME = "goals"
LABEL = "goals_scored"

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
    """Goals per 90 minutes."""
    return model.rate(df)
