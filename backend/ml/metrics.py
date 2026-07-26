"""Evaluation metrics shared by train/ablation: model-agnostic, frame-based."""

import itertools

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def points_metrics(
    frame: pd.DataFrame, preds: np.ndarray, target: str = "total_points"
) -> dict:
    y = frame[target].to_numpy(dtype=float)
    err = np.abs(y - preds)
    out = {
        "mae": float(err.mean()),
        "rmse": float(np.sqrt(((y - preds) ** 2).mean())),
    }
    tmp = frame.assign(_pred=preds, _err=err)
    top50 = tmp.sort_values("_pred", ascending=False).groupby("gameweek").head(50)
    out["mae_top50"] = float(top50["_err"].mean())
    rhos = [
        spearmanr(g[target], g["_pred"]).statistic
        for _, g in tmp.groupby("gameweek")
        if g["_pred"].nunique() > 1
    ]
    out["spearman_per_gw"] = float(np.nanmean(rhos))
    out["mae_by_position"] = {
        POSITION_NAMES.get(p, str(p)): float(g["_err"].mean())
        for p, g in tmp.groupby("position")
    }
    return out


def multiclass_log_loss(y: np.ndarray, probs: np.ndarray) -> float:
    eps = 1e-9
    return float(-np.log(probs[np.arange(len(y)), y] + eps).mean())


HAUL = 10  # points that win a gameweek
BIG_RETURN = 8  # the tail v3 has to price better than v2
BLANK = 2


def early_season_metrics(
    frame: pd.DataFrame, preds: np.ndarray, max_gameweek: int = 8
) -> dict:
    """The same point metrics restricted to the opening gameweeks — where empty
    rolling windows do their damage, and so the only place the form-shrinkage
    work has to win."""
    mask = (frame["gameweek"] <= max_gameweek).to_numpy()
    if mask.sum() < 100:
        return {}
    out = points_metrics(frame[mask], preds[mask])
    out["n"] = int(mask.sum())
    return out


def tail_metrics(frame: pd.DataFrame, preds: np.ndarray) -> dict:
    """How well the big scores are priced. A model can win on MAE by shading
    every prediction toward the mean, which is exactly the wrong trade for
    picking a captain, so the tail is scored separately."""
    y = frame["total_points"].to_numpy(dtype=float)
    out: dict[str, float] = {}
    for label, mask in (
        (f"hauls_ge{BIG_RETURN}", y >= BIG_RETURN),
        (f"hauls_ge{HAUL}", y >= HAUL),
    ):
        if mask.sum() < 20:
            continue
        err = y[mask] - preds[mask]
        out[f"rmse_{label}"] = float(np.sqrt((err**2).mean()))
        out[f"mae_{label}"] = float(np.abs(err).mean())
        out[f"n_{label}"] = int(mask.sum())
    return out


def reliability_curve(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    """Predicted vs empirical rate in equal-width probability bins. Bins with
    too little support are dropped rather than reported as noise."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    edges = np.linspace(0.0, max(float(p.max()), 1e-6), bins + 1)
    out = []
    for lo, hi in itertools.pairwise(edges):
        mask = (p >= lo) & (p < hi if hi < edges[-1] else p <= hi)
        if mask.sum() < 50:
            continue
        out.append(
            {
                "bin": [round(float(lo), 4), round(float(hi), 4)],
                "n": int(mask.sum()),
                "predicted": round(float(p[mask].mean()), 4),
                "empirical": round(float(y[mask].mean()), 4),
            }
        )
    return out


def probability_metrics(
    frame: pd.DataFrame, probs: np.ndarray, threshold: int = HAUL, bins: int = 10
) -> dict:
    """Calibration of P(points >= threshold): Brier, log loss, base rate and the
    reliability curve behind them."""
    y = (frame["total_points"].to_numpy(dtype=float) >= threshold).astype(float)
    p = np.clip(np.asarray(probs, dtype=float), 1e-6, 1 - 1e-6)
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "logloss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "predicted_rate": float(p.mean()),
        "empirical_rate": float(y.mean()),
        "reliability": reliability_curve(p, y, bins),
    }


def quantile_metrics(
    frame: pd.DataFrame, q10: np.ndarray, q50: np.ndarray, q90: np.ndarray
) -> dict:
    """Pinball loss at each quantile plus the realised coverage of the p10-p90
    band, which should sit near 80%."""
    y = frame["total_points"].to_numpy(dtype=float)

    def pinball(q: np.ndarray, tau: float) -> float:
        diff = y - q
        return float(np.mean(np.maximum(tau * diff, (tau - 1) * diff)))

    return {
        "pinball_p10": pinball(np.asarray(q10, dtype=float), 0.1),
        "pinball_p50": pinball(np.asarray(q50, dtype=float), 0.5),
        "pinball_p90": pinball(np.asarray(q90, dtype=float), 0.9),
        "coverage_p10_p90": float(np.mean((y >= q10) & (y <= q90))),
    }
