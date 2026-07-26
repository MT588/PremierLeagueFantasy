"""Backtest metrics: model vs naive baselines on a held-out season."""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ml.features_v1 import FEATURES, TARGET


def _metrics(y_true: pd.Series, y_pred: np.ndarray, frame: pd.DataFrame) -> dict:
    err = np.abs(y_true.to_numpy() - y_pred)
    out = {
        "mae": float(err.mean()),
        "rmse": float(np.sqrt(((y_true.to_numpy() - y_pred) ** 2).mean())),
    }
    # MAE over the 50 highest-predicted players per gameweek (the picks that matter)
    tmp = frame.assign(_pred=y_pred, _err=err)
    top50 = tmp.sort_values("_pred", ascending=False).groupby("gameweek").head(50)
    out["mae_top50"] = float(top50["_err"].mean())
    # mean per-gameweek Spearman rank correlation
    rhos = [
        spearmanr(g[TARGET], g["_pred"]).statistic
        for _, g in tmp.groupby("gameweek")
        if g["_pred"].nunique() > 1
    ]
    out["spearman_per_gw"] = float(np.nanmean(rhos))
    # per-position MAE
    out["mae_by_position"] = {
        {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}[p]: float(g["_err"].mean())
        for p, g in tmp.groupby("position")
    }
    return out


def evaluation_report(model, test: pd.DataFrame) -> dict:
    y = test[TARGET]
    pred = model.predict(test[FEATURES], num_iteration=model.best_iteration)
    baseline_last5 = test["points_avg_5"].fillna(0).to_numpy()
    baseline_pos = test.groupby("position")[TARGET].transform("mean").to_numpy()
    return {
        "test_rows": len(test),
        "model": _metrics(y, pred, test),
        "baseline_last5": _metrics(y, baseline_last5, test),
        "baseline_position_mean": _metrics(y, baseline_pos, test),
    }
