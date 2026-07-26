"""Bonus points, two ways — and the walk-forward decides which ships.

Bonus is not an independent per-player quantity: the three bonus points in a
match go to the top three BPS scores *in that match*. So the honest model is
indirect:

  1. predict each player's BPS,
  2. rank the players within the fixture,
  3. map rank to the empirical bonus distribution.

The direct alternative — regress `bonus` on features and ignore the competition
— is simpler and is what v2 effectively did inside its single regressor. Both
are fitted, both produce a *distribution* (the direct route buckets its own
predictions instead of ranking), and ml/train_v3.py picks the one with the lower
held-out error. Symmetry matters: a route that only produced a point estimate
could not be compared fairly, and could not be simulated at all.

**Bonus is conditioned on the returns drawn in the same simulation.** A player
who has just scored twice is not "probably third in the BPS table" — he is
almost certainly first. Sampling bonus independently of the goals and assists
drawn in the same iteration severs that link and visibly thins the haul tail,
which is the one part of the distribution v3 exists to get right. So the fitted
distribution is P(bonus | bucket, returns), where returns is the player's goals
plus assists capped at 2, and the simulator looks it up per draw.
"""

import logging
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.components.base import NUM_BOOST_ROUND, played
from ml.features import FEATURES_V3

log = logging.getLogger(__name__)

NAME = "bonus"
FEATURES = list(FEATURES_V3)

# Ranks beyond this all behave the same (essentially never any bonus), so they
# share one bucket instead of splitting the sample thinner and thinner.
MAX_RANK = 8

PARAMS: dict = {
    "objective": "regression",
    "metric": "l2",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "verbosity": -1,
}


#: Returns (goals + assists) are capped here; beyond two the bonus outcome
#: barely changes and the buckets would get too thin to estimate.
MAX_RETURNS = 2


@dataclass
class BonusModel:
    """Both candidates plus their fitted distributions.

    `source` selects which bucketing is live; ml/train_v3.py sets it from
    held-out error. `rank_distribution` is keyed by (bucket, returns).
    """

    bps_model: lgb.Booster
    direct_model: lgb.Booster
    best_iteration_bps: int
    best_iteration_direct: int
    source: str = "bps"
    #: (bucket, returns) -> {bonus points -> probability}
    rank_distribution: dict[tuple[int, int], dict[int, float]] = field(
        default_factory=dict
    )
    #: bucket edges for the direct route's predicted-bonus deciles
    direct_edges: list[float] = field(default_factory=list)

    def expectation(self) -> dict[tuple[int, int], float]:
        return {
            key: sum(points * p for points, p in dist.items())
            for key, dist in self.rank_distribution.items()
        }

    def buckets(self, df: pd.DataFrame, features: list[str] | None = None) -> np.ndarray:
        """The live route's bucket per row."""
        if self.source == "direct":
            pred = self.direct_model.predict(
                df[features or self.direct_model.feature_name()],
                num_iteration=self.best_iteration_direct or None,
            )
            edges = np.asarray(self.direct_edges, dtype=float)
            if edges.size == 0:
                return np.zeros(len(df), dtype=int)
            return np.clip(
                np.digitize(pred, edges), 0, max(len(edges), 1)
            ).astype(int)
        return fixture_rank(df, predicted_bps(self, df, features))


def _train_one(
    fit: pd.DataFrame, valid: pd.DataFrame, features: list[str], label: str
) -> tuple[lgb.Booster, int]:
    dtrain = lgb.Dataset(
        fit[features],
        label=fit[label].fillna(0).to_numpy(dtype=float),
        categorical_feature=["position"] if "position" in features else [],
    )
    dvalid = lgb.Dataset(
        valid[features],
        label=valid[label].fillna(0).to_numpy(dtype=float),
        reference=dtrain,
    )
    booster = lgb.train(
        PARAMS,
        dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    return booster, booster.best_iteration or NUM_BOOST_ROUND


def fixture_rank(df: pd.DataFrame, predicted_bps: np.ndarray) -> np.ndarray:
    """1-based rank of predicted BPS within each fixture, capped at MAX_RANK.

    Both teams' players share a fixture id, which is exactly the competition
    bonus points are awarded over.
    """
    frame = pd.DataFrame(
        {
            "season_id": df["season_id"].to_numpy(),
            "fixture": df["fpl_fixture_id"].to_numpy(),
            "bps": np.asarray(predicted_bps, dtype=float),
        }
    )
    ranks = (
        frame.groupby(["season_id", "fixture"])["bps"]
        .rank(ascending=False, method="first")
        .to_numpy()
    )
    return np.clip(np.nan_to_num(ranks, nan=MAX_RANK), 1, MAX_RANK).astype(int)


def returns_bucket(goals: np.ndarray, assists: np.ndarray) -> np.ndarray:
    """Goals plus assists, capped at MAX_RETURNS."""
    return np.clip(
        np.nan_to_num(np.asarray(goals, dtype=float))
        + np.nan_to_num(np.asarray(assists, dtype=float)),
        0,
        MAX_RETURNS,
    ).astype(int)


def fit_distribution(
    df: pd.DataFrame, buckets: np.ndarray
) -> dict[tuple[int, int], dict[int, float]]:
    """Empirical P(bonus | bucket, returns) over the training rows.

    Thin cells fall back to the same bucket pooled over returns, then to the
    same returns pooled over buckets, so a rare combination degrades to a
    coarser estimate instead of a fabricated one.
    """
    actual = df["bonus"].fillna(0).to_numpy(dtype=float).astype(int)
    returns = returns_bucket(df["goals_scored"], df["assists"])

    def tally(mask: np.ndarray) -> dict[int, float] | None:
        if mask.sum() < 40:
            return None
        values, counts = np.unique(actual[mask], return_counts=True)
        total = counts.sum()
        return {int(v): float(c / total) for v, c in zip(values, counts)}

    out: dict[tuple[int, int], dict[int, float]] = {}
    for bucket in np.unique(buckets):
        for r in range(MAX_RETURNS + 1):
            dist = (
                tally((buckets == bucket) & (returns == r))
                or tally(buckets == bucket)
                or tally(returns == r)
                or {0: 1.0}
            )
            out[(int(bucket), r)] = dist
    return out


def _fit_direct_edges(predictions: np.ndarray) -> list[float]:
    """Decile edges of the direct model's own predictions, so its buckets are
    comparable in granularity to the rank route's."""
    edges = np.unique(np.quantile(predictions, np.linspace(0.1, 0.9, 9)))
    return [float(e) for e in edges]


def _refresh_distribution(model: BonusModel, rows: pd.DataFrame) -> None:
    """Rebuild the bucket edges and the conditional distribution for the live
    route. Feature lists come from the boosters themselves, never from a module
    default — the ablation trains these on a pruned pool."""
    if model.source == "direct":
        pred = model.direct_model.predict(
            rows[model.direct_model.feature_name()],
            num_iteration=model.best_iteration_direct or None,
        )
        model.direct_edges = _fit_direct_edges(np.asarray(pred, dtype=float))
    model.rank_distribution = fit_distribution(rows, model.buckets(rows))


def train(
    fit: pd.DataFrame,
    valid: pd.DataFrame,
    features: list[str] | None = None,
    source: str = "bps",
) -> BonusModel:
    features = features or FEATURES
    fit_rows, valid_rows = played(fit), played(valid)
    bps_model, it_bps = _train_one(fit_rows, valid_rows, features, "bps")
    direct_model, it_direct = _train_one(fit_rows, valid_rows, features, "bonus")
    model = BonusModel(
        bps_model=bps_model,
        direct_model=direct_model,
        best_iteration_bps=it_bps,
        best_iteration_direct=it_direct,
        source=source,
    )
    _refresh_distribution(model, fit_rows)
    return model


def set_source(model: BonusModel, source: str, rows: pd.DataFrame) -> None:
    """Switch route and refit the distribution to match it."""
    model.source = source
    _refresh_distribution(model, played(rows))


def refit(
    full: pd.DataFrame,
    best_iteration_bps: int,
    best_iteration_direct: int,
    features: list[str] | None = None,
    source: str = "bps",
) -> BonusModel:
    features = features or FEATURES
    rows = played(full)
    boosters = {}
    for label, rounds in (("bps", best_iteration_bps), ("bonus", best_iteration_direct)):
        dtrain = lgb.Dataset(
            rows[features],
            label=rows[label].fillna(0).to_numpy(dtype=float),
            categorical_feature=["position"] if "position" in features else [],
        )
        boosters[label] = lgb.train(
            PARAMS, dtrain, num_boost_round=max(rounds, 10)
        )
    model = BonusModel(
        bps_model=boosters["bps"],
        direct_model=boosters["bonus"],
        best_iteration_bps=0,
        best_iteration_direct=0,
        source=source,
    )
    _refresh_distribution(model, rows)
    return model


def predicted_bps(
    model: BonusModel, df: pd.DataFrame, features: list[str] | None = None
) -> np.ndarray:
    features = features or model.bps_model.feature_name()
    return np.asarray(
        model.bps_model.predict(
            df[features], num_iteration=model.best_iteration_bps or None
        ),
        dtype=float,
    )


def expected_bonus(
    model: BonusModel, buckets: np.ndarray, returns_probs: np.ndarray
) -> np.ndarray:
    """E[bonus] marginalised over the returns distribution.

    `returns_probs` is (rows, MAX_RETURNS + 1): the chance the player finishes
    with 0, 1, or 2+ goals and assists. Used for the analytic expectation and
    the per-component breakdown shown in the app; the simulator draws instead.
    """
    expectation = model.expectation()
    out = np.zeros(len(buckets))
    for r in range(MAX_RETURNS + 1):
        per_row = np.array(
            [expectation.get((int(b), r), 0.0) for b in buckets], dtype=float
        )
        out += returns_probs[:, r] * per_row
    return out


def predict(
    model: BonusModel, df: pd.DataFrame, features: list[str] | None = None
) -> np.ndarray:
    """Expected bonus for a full appearance, using the observed returns.

    This is the fold-selection metric: it asks how well each route prices the
    bonus a player actually got, so the two candidates are judged on the same
    quantity.
    """
    buckets = model.buckets(df, features)
    returns = returns_bucket(df["goals_scored"], df["assists"])
    expectation = model.expectation()
    return np.array(
        [expectation.get((int(b), int(r)), 0.0) for b, r in zip(buckets, returns)],
        dtype=float,
    )


def sample(
    model: BonusModel,
    buckets: np.ndarray,
    returns: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw bonus points per simulation cell, conditioned on that cell's bucket
    and the returns drawn in the same iteration."""
    draws = np.zeros(returns.shape)
    bucket_grid = np.broadcast_to(buckets.reshape(-1, 1), returns.shape)
    for (bucket, r), dist in model.rank_distribution.items():
        mask = (bucket_grid == bucket) & (returns == r)
        count = int(mask.sum())
        if not count:
            continue
        values = np.array(sorted(dist), dtype=float)
        probs = np.array([dist[int(v)] for v in values], dtype=float)
        draws[mask] = rng.choice(values, size=count, p=probs / probs.sum())
    return draws


def distribution_to_json(model: BonusModel) -> dict:
    """(bucket, returns) keys flattened to "bucket:returns" so the map survives
    a JSON round trip."""
    return {
        f"{bucket}:{returns}": {str(p): v for p, v in dist.items()}
        for (bucket, returns), dist in model.rank_distribution.items()
    }


def distribution_from_json(payload: dict) -> dict[tuple[int, int], dict[int, float]]:
    out: dict[tuple[int, int], dict[int, float]] = {}
    for key, dist in payload.items():
        bucket, returns = key.split(":")
        out[(int(bucket), int(returns))] = {int(p): v for p, v in dist.items()}
    return out
