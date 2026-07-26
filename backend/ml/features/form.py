"""Rolling-form features (all lagged: shift(1) before every window)."""

import pandas as pd

ROLL_WINDOWS = (3, 5, 10)

FEATURES = [
    *[f"points_avg_{w}" for w in ROLL_WINDOWS],
    *[f"minutes_avg_{w}" for w in ROLL_WINDOWS],
    "goals_sum_5", "assists_sum_5", "bonus_avg_5", "bps_avg_5", "ict_avg_5",
    "xg90_5", "xa90_5", "xgi90_5", "xgi90_10",
    "points_ewma_hl3", "points_ewma_hl8", "xgi90_ewma_hl5", "minutes_ewma_hl3",
    "season_ppg",
]


def add(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("player_code", sort=False)

    for w in ROLL_WINDOWS:
        df[f"points_avg_{w}"] = g["total_points"].transform(
            lambda s, w=w: s.shift(1).rolling(w, min_periods=1).mean()
        )
        df[f"minutes_avg_{w}"] = g["minutes"].transform(
            lambda s, w=w: s.shift(1).rolling(w, min_periods=1).mean()
        )
    df["goals_sum_5"] = g["goals_scored"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).sum()
    )
    df["assists_sum_5"] = g["assists"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).sum()
    )
    df["bonus_avg_5"] = g["bonus"].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    df["bps_avg_5"] = g["bps"].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    df["ict_avg_5"] = g["ict_index"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )

    for w in (5, 10):
        min_sum = g["minutes"].transform(lambda s, w=w: s.shift(1).rolling(w, min_periods=1).sum())
        for out, col in (
            (f"xg90_{w}", "expected_goals"),
            (f"xa90_{w}", "expected_assists"),
            (f"xgi90_{w}", "expected_goal_involvements"),
        ):
            if w == 10 and out != "xgi90_10":
                continue
            stat_sum = g[col].transform(
                lambda s, w=w: s.shift(1).rolling(w, min_periods=1).sum()
            )
            df[out] = (stat_sum / min_sum.clip(lower=1)) * 90

    for hl in (3, 8):
        df[f"points_ewma_hl{hl}"] = g["total_points"].transform(
            lambda s, hl=hl: s.shift(1).ewm(halflife=hl, min_periods=1).mean()
        )
    df["minutes_ewma_hl3"] = g["minutes"].transform(
        lambda s: s.shift(1).ewm(halflife=3, min_periods=1).mean()
    )
    xgi_ewma = g["expected_goal_involvements"].transform(
        lambda s: s.shift(1).ewm(halflife=5, min_periods=1).mean()
    )
    min_ewma = g["minutes"].transform(
        lambda s: s.shift(1).ewm(halflife=5, min_periods=1).mean()
    )
    df["xgi90_ewma_hl5"] = (xgi_ewma / min_ewma.clip(lower=1)) * 90

    grp_season = df.groupby(["player_code", "season_id"], sort=False)
    cum_pts = grp_season["total_points"].transform(lambda s: s.shift(1).cumsum())
    cum_games = grp_season.cumcount().astype(float)
    df["season_ppg"] = cum_pts / cum_games.where(cum_games > 0)
    return df
