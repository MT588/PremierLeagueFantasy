"""Defensive contribution: P(clearing the positional threshold).

The 2025-26 rule pays 2 points for reaching 10 defensive actions as a defender
(tackles + clearances/blocks/interceptions) or 12 as a midfielder or forward
(those plus recoveries). Keepers do not score it.

Because it is a threshold, not a count, this is a classifier: the quantity that
matters is P(actions >= threshold), and the threshold is read from
ml/scoring.py so the derived-from-data value is the one used.

**One season of history exists.** The underlying counts arrived with the rule in
2025-26 — checked against vaastav's 2023-24 and 2024-25 files, which have no
such columns — so:

  - a fold whose training seasons predate 2025-26 cannot fit this at all.
    `train` returns None there and the component contributes nothing, which
    leaves v3 exactly as blind as v2 on that fold rather than quietly leaking
    the test season's data into the fit;
  - the component's real out-of-sample test is the intra-2025-26 fold in
    ml/train_v3.py (train through GW19, predict GW20-38).
"""

import itertools
import logging

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml import scoring
from ml.components.base import BINARY_PARAMS, resolve_features, train_binary
from ml.features import FEATURES_V3
from ml.features.form_eb import DC_FEATURES

log = logging.getLogger(__name__)

NAME = "defcon"
LABEL = "defensive_contribution"
MIN_ROWS = 2000

EXTRAS = list(DC_FEATURES)
# resolve_features rather than concatenation: eb_dc90 is in the shared pool as
# well as in this component's extras, and LightGBM rejects a duplicated name.
FEATURES = resolve_features(None, FEATURES_V3, EXTRAS)


def threshold_hit(df: pd.DataFrame) -> np.ndarray:
    """Did the player reach his position's threshold in this match?"""
    thresholds = np.zeros(5)
    for pos, value in scoring.DC_THRESHOLDS.items():
        thresholds[pos] = value if value > 0 else np.inf
    counts = df[LABEL].to_numpy(dtype=float)
    positions = df["position"].to_numpy(dtype=int)
    return (counts >= thresholds[positions]).astype(float)


def _usable(df: pd.DataFrame) -> pd.DataFrame:
    """Rows the threshold probability is estimated from: the stat exists and the
    player played an hour, so the probability is conditional on a real
    appearance. Partial appearances are handled by `fit_minutes_scaling`."""
    return df[df[LABEL].notna() & (df["minutes"] >= 60)]


#: Minutes buckets the scaling curve is measured over.
MINUTES_BUCKETS = (1, 15, 30, 45, 60)


def fit_minutes_scaling(df: pd.DataFrame) -> dict[int, float]:
    """How the chance of clearing the threshold falls away on a short outing.

    Defensive actions accumulate with time on the pitch against a fixed
    threshold, so the hit rate collapses far faster than pro-rata: this measures
    the collapse instead of assuming a shape. Returns bucket lower bound ->
    multiplier relative to a 60+ minute appearance.
    """
    rows = df[df[LABEL].notna() & (df["minutes"] > 0)]
    if rows.empty:
        return {}
    hits = threshold_hit(rows)
    minutes = rows["minutes"].to_numpy(dtype=float)
    baseline = hits[minutes >= 60].mean() if (minutes >= 60).any() else 0.0
    if baseline <= 0:
        return {}
    out: dict[int, float] = {}
    edges = list(MINUTES_BUCKETS) + [10_000]
    for lo, hi in itertools.pairwise(edges):
        mask = (minutes >= lo) & (minutes < hi)
        out[lo] = float(hits[mask].mean() / baseline) if mask.sum() >= 100 else 0.0
    out[MINUTES_BUCKETS[-1]] = 1.0
    return out


def _split_for_early_stopping(
    fit_rows: pd.DataFrame, valid_rows: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Early-stopping split for a component whose stat is younger than the folds.

    The validation season a fold hands down (the last complete one before the
    test season) predates the defensive-contribution rule, so it contains no
    usable rows and cannot validate this model. When that happens the tail of
    the DC-bearing training rows is held back instead, split by gameweek so the
    validation slice is still later in time than what it validates.
    """
    if len(valid_rows) >= 200:
        return fit_rows, valid_rows
    if fit_rows.empty:
        return fit_rows, valid_rows
    cutoff = fit_rows["gameweek"].quantile(0.8)
    head = fit_rows[fit_rows["gameweek"] <= cutoff]
    tail = fit_rows[fit_rows["gameweek"] > cutoff]
    if len(tail) < 100 or len(head) < MIN_ROWS:
        return fit_rows, valid_rows
    log.info(
        "defcon: validation season has no defensive-contribution data — "
        "holding back gameweeks above %.0f of the training rows instead", cutoff
    )
    return head, tail


def train(
    fit: pd.DataFrame, valid: pd.DataFrame, features: list[str] | None = None
) -> lgb.Booster | None:
    features = resolve_features(features, FEATURES_V3, EXTRAS)
    fit_rows, valid_rows = _split_for_early_stopping(_usable(fit), _usable(valid))
    if len(fit_rows) < MIN_ROWS or len(valid_rows) < 100:
        log.info(
            "defcon: only %d usable training rows — component disabled for this fold",
            len(fit_rows),
        )
        return None
    return train_binary(
        fit_rows,
        valid_rows,
        features,
        threshold_hit(fit_rows),
        threshold_hit(valid_rows),
        params={"min_data_in_leaf": 100},
    )


def refit(
    full: pd.DataFrame, best_iteration: int, features: list[str] | None = None
) -> lgb.Booster | None:
    features = resolve_features(features, FEATURES_V3, EXTRAS)
    rows = _usable(full)
    if len(rows) < MIN_ROWS:
        return None
    dtrain = lgb.Dataset(
        rows[features],
        label=threshold_hit(rows),
        categorical_feature=["position"] if "position" in features else [],
    )
    return lgb.train(
        {**BINARY_PARAMS, "min_data_in_leaf": 100},
        dtrain,
        num_boost_round=max(best_iteration, 10),
    )


def predict(model: lgb.Booster | None, df: pd.DataFrame) -> np.ndarray:
    """P(threshold reached | played the full match). Zero when the component is
    unavailable for the fold, and zero for keepers, who cannot score it.

    The rate is conditional on a full appearance: the simulator scales it by the
    minutes actually drawn, since a player who comes on for twenty minutes has
    little chance of ten defensive actions.
    """
    if model is None:
        return np.zeros(len(df))
    probs = model.predict(
        df[model.feature_name()], num_iteration=model.best_iteration or None
    )
    scores_dc = np.array(
        [scoring.DC_THRESHOLDS.get(p, 0) > 0 for p in range(5)], dtype=float
    )
    return np.clip(probs, 0.0, 1.0) * scores_dc[df["position"].to_numpy(dtype=int)]
