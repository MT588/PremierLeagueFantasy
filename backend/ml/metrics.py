"""Evaluation metrics shared by train/ablation: model-agnostic, frame-based."""

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
