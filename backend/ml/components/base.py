"""Shared machinery for the count components.

Every count model here predicts a **per-90 rate**, not a per-match count. That
is what makes minutes and scoring separable: the Monte-Carlo simulator samples a
minutes class first and then scales the rate by the minutes drawn, so a cameo
and a full start come out of one model instead of needing the empirical cameo
fudge v2 applied after the fact.

The mechanism is LightGBM's `init_score`, used as a Poisson offset: training
with `init_score = log(minutes / 90)` makes the model learn a log-rate, and
`predict` (which does not re-apply the offset) returns the rate directly.

Poisson fixes the variance at the mean, which understates how lumpy football is
— the tail matters here, because P(haul) is the thing v3 exists to get right.
So each fitted mean also carries a negative-binomial dispersion estimated per
position, and ml/train_v3.py picks the family per component on held-out folds.
"""

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

PARAMS: dict = {
    "objective": "poisson",
    "metric": "poisson",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "verbosity": -1,
}

BINARY_PARAMS: dict = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "verbosity": -1,
}

NUM_BOOST_ROUND = 1500
EARLY_STOPPING = 100

# A rate is only meaningful over enough minutes to measure it. With a Poisson
# offset a five-minute cameo that produced a goal asserts a rate of 18 per 90,
# and that leverage is noise, not signal: raising the training floor to 30
# minutes cut fold MAE from 0.951 to 0.945. Prediction is unaffected — every row
# still gets a rate, whatever minutes it is expected to play.
MIN_MINUTES = 30
# Dispersion candidates for the negative binomial: 0 is the Poisson limit.
ALPHA_GRID = (0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.5)


@dataclass
class CountModel:
    """A fitted per-90 rate model plus the count law used to sample from it."""

    booster: lgb.Booster
    features: list[str]
    best_iteration: int
    alpha: dict[int, float] = field(default_factory=dict)
    family: str = "poisson"

    def rate(self, df: pd.DataFrame) -> np.ndarray:
        """Expected events per 90 minutes."""
        raw = self.booster.predict(
            df[self.features], num_iteration=self.best_iteration or None
        )
        return np.clip(np.asarray(raw, dtype=float), 0.0, None)

    def dispersion_for(self, position: np.ndarray) -> np.ndarray:
        if self.family == "poisson" or not self.alpha:
            return np.zeros(np.shape(position))
        lut = np.zeros(5)
        for pos, value in self.alpha.items():
            lut[pos] = value
        return lut[np.asarray(position, dtype=int)]


def resolve_features(
    features: list[str] | None, default_pool: list[str], extras: list[str]
) -> list[str]:
    """Combine a caller-supplied pool with a component's own inputs.

    The ablation varies the shared pool; a component's specific inputs (a
    keeper's save rate, the defensive-action rates) are not part of that
    experiment and must survive it, or the ablation would be measuring a
    crippled component rather than a feature group.
    """
    pool = list(default_pool if features is None else features)
    return pool + [f for f in extras if f not in pool]


def _exposure(df: pd.DataFrame) -> np.ndarray:
    return np.clip(df["minutes"].to_numpy(dtype=float) / 90.0, 1e-3, None)


def played(df: pd.DataFrame, positions: tuple[int, ...] | None = None) -> pd.DataFrame:
    """Rows a rate can be estimated from: the player was on the pitch."""
    mask = df["minutes"].fillna(0) >= MIN_MINUTES
    if positions:
        mask &= df["position"].isin(positions)
    return df[mask]


def train_rate(
    fit: pd.DataFrame,
    valid: pd.DataFrame,
    features: list[str],
    label: str,
    positions: tuple[int, ...] | None = None,
    params: dict | None = None,
) -> CountModel:
    """Fit a per-90 rate with minutes as a Poisson offset, early-stopping on the
    validation season."""
    fit, valid = played(fit, positions), played(valid, positions)
    dtrain = lgb.Dataset(
        fit[features],
        label=fit[label].fillna(0).to_numpy(dtype=float),
        init_score=np.log(_exposure(fit)),
        categorical_feature=["position"] if "position" in features else [],
    )
    dvalid = lgb.Dataset(
        valid[features],
        label=valid[label].fillna(0).to_numpy(dtype=float),
        init_score=np.log(_exposure(valid)),
        reference=dtrain,
    )
    booster = lgb.train(
        {**PARAMS, **(params or {})},
        dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)],
    )
    model = CountModel(
        booster=booster,
        features=features,
        best_iteration=booster.best_iteration or NUM_BOOST_ROUND,
    )
    model.alpha = fit_dispersion(model, fit, label)
    return model


def refit_rate(
    full: pd.DataFrame,
    best_iteration: int,
    features: list[str],
    label: str,
    positions: tuple[int, ...] | None = None,
    alpha: dict[int, float] | None = None,
    family: str = "poisson",
    params: dict | None = None,
) -> CountModel:
    """Refit on every available season at the iteration count the fold chose."""
    full = played(full, positions)
    dtrain = lgb.Dataset(
        full[features],
        label=full[label].fillna(0).to_numpy(dtype=float),
        init_score=np.log(_exposure(full)),
        categorical_feature=["position"] if "position" in features else [],
    )
    booster = lgb.train(
        {**PARAMS, **(params or {})},
        dtrain,
        num_boost_round=max(best_iteration, 10),
    )
    model = CountModel(
        booster=booster,
        features=features,
        best_iteration=0,
        family=family,
    )
    model.alpha = alpha if alpha is not None else fit_dispersion(model, full, label)
    return model


def train_binary(
    fit: pd.DataFrame,
    valid: pd.DataFrame,
    features: list[str],
    label: np.ndarray | pd.Series,
    valid_label: np.ndarray | pd.Series,
    params: dict | None = None,
) -> lgb.Booster:
    dtrain = lgb.Dataset(
        fit[features],
        label=np.asarray(label, dtype=float),
        categorical_feature=["position"] if "position" in features else [],
    )
    dvalid = lgb.Dataset(
        valid[features], label=np.asarray(valid_label, dtype=float), reference=dtrain
    )
    return lgb.train(
        {**BINARY_PARAMS, **(params or {})},
        dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)],
    )


def _nb_loglik(y: np.ndarray, mu: np.ndarray, alpha: float) -> float:
    """NB2 log-likelihood; alpha -> 0 is the Poisson limit."""
    from scipy.special import gammaln

    mu = np.clip(mu, 1e-9, None)
    if alpha <= 0:
        return float(np.sum(y * np.log(mu) - mu - gammaln(y + 1)))
    r = 1.0 / alpha
    return float(
        np.sum(
            gammaln(y + r)
            - gammaln(r)
            - gammaln(y + 1)
            + r * np.log(r / (r + mu))
            + y * np.log(mu / (r + mu))
        )
    )


def fit_dispersion(
    model: CountModel, frame: pd.DataFrame, label: str
) -> dict[int, float]:
    """Per-position NB dispersion by maximum likelihood over a small grid.

    Fitted on the training rows only, alongside the mean. Whether it gets used
    is decided per component in ml/train_v3.py by held-out likelihood — the mean
    is identical either way, so this only ever changes the spread.
    """
    rates = model.rate(frame)
    mu = rates * _exposure(frame)
    y = frame[label].fillna(0).to_numpy(dtype=float)
    positions = frame["position"].to_numpy(dtype=int)
    out: dict[int, float] = {}
    for pos in np.unique(positions):
        mask = positions == pos
        if mask.sum() < 500:
            continue
        best = max(ALPHA_GRID, key=lambda a: _nb_loglik(y[mask], mu[mask], a))
        out[int(pos)] = float(best)
    return out


def sample_counts(
    mu: np.ndarray, alpha: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Draw counts with mean `mu`, Poisson where alpha is 0 and negative
    binomial (as a gamma-Poisson mixture) where it is not."""
    mu = np.clip(mu, 0.0, None)
    alpha = np.asarray(alpha, dtype=float)
    overdispersed = alpha > 0
    if not overdispersed.any():
        return rng.poisson(mu)
    shape = np.where(overdispersed, 1.0 / np.where(overdispersed, alpha, 1.0), 1.0)
    scale = np.where(overdispersed, mu * alpha, 1.0)
    lam = np.where(overdispersed, rng.gamma(shape, scale), mu)
    return rng.poisson(lam)


def holdout_loglik(
    model: CountModel, frame: pd.DataFrame, label: str, family: str
) -> float:
    """Mean held-out log-likelihood of the count law — the number that decides
    Poisson vs negative binomial for this component."""
    frame = played(frame)
    if frame.empty:
        return float("nan")
    mu = model.rate(frame) * _exposure(frame)
    y = frame[label].fillna(0).to_numpy(dtype=float)
    positions = frame["position"].to_numpy(dtype=int)
    total = 0.0
    for pos in np.unique(positions):
        mask = positions == pos
        alpha = model.alpha.get(int(pos), 0.0) if family == "nb" else 0.0
        total += _nb_loglik(y[mask], mu[mask], alpha)
    return total / len(frame)
