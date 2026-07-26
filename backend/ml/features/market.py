"""Elo-implied match outcome probabilities (calibrated once vs betting odds
in ml/elo_prob.py — odds themselves can't be inference features)."""

import numpy as np
import pandas as pd

from ml import elo_prob

FEATURES = ["p_win_elo", "p_draw_elo", "p_loss_elo"]


def add(df: pd.DataFrame) -> pd.DataFrame:
    params = elo_prob.load_params()
    hfa, c, s = params["hfa"], params["c"], params["s"]

    home_diff = np.where(
        df["was_home"].astype(bool),
        df["own_elo"] - df["opp_elo"],
        df["opp_elo"] - df["own_elo"],
    ).astype(float)
    valid = ~np.isnan(home_diff)
    probs = np.full((len(df), 3), np.nan)
    if valid.any():
        probs[valid] = elo_prob.elo_probs(home_diff[valid], hfa, c, s)

    is_home = df["was_home"].astype(bool).to_numpy()
    df["p_win_elo"] = np.where(is_home, probs[:, 0], probs[:, 2])
    df["p_draw_elo"] = probs[:, 1]
    df["p_loss_elo"] = np.where(is_home, probs[:, 2], probs[:, 0])
    return df
