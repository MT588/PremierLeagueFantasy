"""Fit the empirical-Bayes blend weights instead of choosing them.

Each shrunk statistic in ml/features/form_eb.py mixes a current-season rate with
a prior at weight `n / (n + k)`. `k` is the number of matches (or 90s) of
current-season evidence that earns the prior an equal say, and it is fitted
here: for every row, the blend is built strictly from earlier matches, so the
row's own realised statistic is an honest out-of-sample target. The `k` that
predicts it best across the training seasons wins.

Counts are scored by Poisson deviance (the loss the component models are
trained under) and per-match means by squared error. Callers must pass a frame
restricted to training-fold seasons — nothing here enforces that, and
train_v3.py is the only production caller.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ml.features import form_eb

log = logging.getLogger(__name__)

GRID: tuple[float, ...] = (
    0.25,
    0.5,
    1.0,
    2.0,
    3.0,
    5.0,
    8.0,
    12.0,
    20.0,
    30.0,
    50.0,
)

# A blend is only informative once the player is on the pitch; rotation noise
# would otherwise dominate the fit.
MIN_MINUTES = 1


def _poisson_deviance(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.clip(mu, 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / mu), 0.0)
    return float(2.0 * np.mean(term - (y - mu)))


def _loss_for(stat: form_eb.Stat, frame: pd.DataFrame, k: float) -> float | None:
    cur = frame[f"_eb_cur_{stat.name}"]
    prior = frame[f"_eb_prior_{stat.name}"]
    n = frame[f"_eb_n_{stat.name}"].fillna(0.0)
    w = n / (n + k)
    blended = np.where(
        cur.isna() & prior.isna(),
        np.nan,
        np.where(
            cur.isna(),
            prior,
            np.where(prior.isna(), cur, w * cur.fillna(0.0) + (1 - w) * prior.fillna(0.0)),
        ),
    )

    target = frame[stat.col] if stat.col in frame.columns else None
    if target is None:
        return None
    usable = np.isfinite(blended) & target.notna().to_numpy()
    if usable.sum() < 500:
        return None

    pred = np.asarray(blended, dtype=float)[usable]
    y = target.to_numpy(dtype=float)[usable]
    if stat.per == "90":
        exposure = frame["minutes"].to_numpy(dtype=float)[usable] / 90.0
        return _poisson_deviance(y, np.clip(pred, 0, None) * exposure)
    return float(np.mean((y - pred) ** 2))


def fit_ks(
    frame: pd.DataFrame,
    stats: tuple[form_eb.Stat, ...] = form_eb.STATS,
    grid: tuple[float, ...] = GRID,
) -> dict[str, float]:
    """Grid-search one `k` per statistic on the rows given. Statistics with too
    little evidence keep their documented default."""
    played = frame[frame["minutes"].fillna(0) >= MIN_MINUTES]
    out: dict[str, float] = {}
    for stat in stats:
        # searching the default too means a fit can never come out worse than
        # the documented fallback, and makes the log comparison meaningful
        candidates = tuple(sorted(set(grid) | {stat.default_k}))
        losses = {k: _loss_for(stat, played, k) for k in candidates}
        scored = {k: v for k, v in losses.items() if v is not None}
        if not scored:
            out[stat.name] = stat.default_k
            log.info("shrinkage %-12s no usable rows -> default k=%.1f", stat.name, stat.default_k)
            continue
        best = min(scored, key=lambda k: scored[k])
        out[stat.name] = best
        log.info(
            "shrinkage %-12s k=%-5.1f loss=%.5f (default %.1f -> %.5f)",
            stat.name,
            best,
            scored[best],
            stat.default_k,
            scored.get(stat.default_k, float("nan")),
        )
    return out


def save(path: Path, ks: dict[str, float]) -> None:
    path.write_text(json.dumps(ks, indent=2))


def load(path: Path) -> dict[str, float]:
    if not path.exists():
        return dict(form_eb.DEFAULT_KS)
    return {k: float(v) for k, v in json.loads(path.read_text()).items()}
