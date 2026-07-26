"""Availability/rotation and fixture-context features carried over from v1.

Note: player_seasons.status is an end-of-season snapshot for historical
seasons, so it is deliberately NOT a model feature (train/inference skew);
availability is applied as a hard gate at inference time instead.
"""

import pandas as pd

FEATURES = [
    "was_home_i",
    "position",
    "value",
    "new_season",
    "started_last",
    "start_share_5",
    "start_share_10",
    "played_share_5",
    "fdr",
    "own_attack",
    "own_overall",
    "opp_defence",
    "opp_overall",
]


def add(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("player_code", sort=False)
    df["was_home_i"] = df["was_home"].astype(float)
    df["position"] = df["position"].astype(int)
    df["new_season"] = (
        g["season_id"].transform(lambda s: s.ne(s.shift(1))).astype(float)
    )
    df["started_last"] = (g["minutes"].transform(lambda s: s.shift(1)) >= 60).astype(
        float
    )
    started = (df["minutes"] >= 60).astype(float).where(df["minutes"].notna())
    played = (df["minutes"] > 0).astype(float).where(df["minutes"].notna())
    df["_started"] = started
    df["_played"] = played
    df["start_share_5"] = g["_started"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )
    df["start_share_10"] = g["_started"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=1).mean()
    )
    df["played_share_5"] = g["_played"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )
    df = df.drop(columns=["_started", "_played"])
    return df
