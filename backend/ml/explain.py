"""Prediction drivers via LightGBM's native SHAP values (pred_contrib)."""

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.features import FEATURE_LABELS, FEATURES

TOP_K = 6


def drivers_for(
    model: lgb.Booster,
    frame: pd.DataFrame,
    minutes_probs: np.ndarray,
    points_pred: np.ndarray,
) -> list[dict]:
    contribs = model.predict(frame[FEATURES], pred_contrib=True)
    out = []
    for i in range(len(frame)):
        row = contribs[i, :-1]  # last column is the expected base value
        top_idx = np.argsort(-np.abs(row))[:TOP_K]
        top = [
            {
                "feature": FEATURES[j],
                "label": FEATURE_LABELS.get(FEATURES[j], FEATURES[j]),
                "value": _clean(frame.iloc[i][FEATURES[j]]),
                "contribution": round(float(row[j]), 3),
            }
            for j in top_idx
            if abs(row[j]) > 0.01
        ]
        out.append(
            {
                "p_start": round(float(minutes_probs[i, 2]), 3),
                "p_cameo": round(float(minutes_probs[i, 1]), 3),
                "expected_if_start": round(float(points_pred[i]), 2),
                "top": top,
            }
        )
    return out


def _clean(v) -> float | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        return None
