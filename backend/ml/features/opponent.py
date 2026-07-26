"""Opponent-specific matchup features: Elo strength, recent defensive record,
position-vs-opponent concessions, and the player's own record vs this club."""

import pandas as pd

from ml.features.context import FeatureContext

FEATURES = [
    "own_elo",
    "opp_elo",
    "elo_diff",
    "opp_goals_conceded_6",
    "opp_cs_rate_10",
    "opp_pts_to_pos_6",
    "vs_opp_ppg",
    "vs_opp_games",
]


def _asof_elo(
    df: pd.DataFrame, ctx: FeatureContext, team_col: str, out: str
) -> pd.DataFrame:
    elo = ctx.club_elo.rename(
        columns={"team_code": team_col, "valid_from": "kickoff_time"}
    ).sort_values("kickoff_time")
    order = df.index
    left = (
        df[[team_col, "kickoff_time"]]
        .reset_index()
        .dropna(subset=["kickoff_time", team_col])
        .sort_values("kickoff_time")
    )
    merged = pd.merge_asof(
        left, elo, on="kickoff_time", by=team_col, direction="backward"
    ).set_index("index")
    df[out] = merged["elo"].reindex(order)
    return df


def _team_defence(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    tf = ctx.team_fixtures[ctx.team_fixtures["finished"]].copy()
    tf = tf.sort_values(["team_code", "kickoff_time"]).reset_index(drop=True)
    g = tf.groupby("team_code", sort=False)
    tf["ga_6"] = g["goals_against"].transform(
        lambda s: s.rolling(6, min_periods=3).mean()
    )
    tf["cs_10"] = g["goals_against"].transform(
        lambda s: s.eq(0).rolling(10, min_periods=5).mean()
    )
    tf = tf.rename(columns={"team_code": "opponent_team_code"}).sort_values(
        "kickoff_time"
    )

    order = df.index
    left = (
        df[["opponent_team_code", "kickoff_time"]]
        .reset_index()
        .dropna(subset=["kickoff_time", "opponent_team_code"])
        .sort_values("kickoff_time")
    )
    merged = pd.merge_asof(
        left,
        tf[["opponent_team_code", "kickoff_time", "ga_6", "cs_10"]],
        on="kickoff_time",
        by="opponent_team_code",
        direction="backward",
        allow_exact_matches=False,
    ).set_index("index")
    df["opp_goals_conceded_6"] = merged["ga_6"].reindex(order)
    df["opp_cs_rate_10"] = merged["cs_10"].reindex(order)
    return df


def _pts_to_position(df: pd.DataFrame) -> pd.DataFrame:
    """Mean FPL points the opponent concedes to starters of each position,
    trailing 6 matches (computed from history rows only)."""
    hist = df[~df["is_inference"] & (df["minutes"] >= 60)]
    conceded = (
        hist.groupby(["opponent_team_code", "kickoff_time", "position"])["total_points"]
        .mean()
        .reset_index()
        .rename(columns={"total_points": "pts_to_pos"})
    )
    conceded = conceded.sort_values(["opponent_team_code", "position", "kickoff_time"])
    g = conceded.groupby(["opponent_team_code", "position"], sort=False)
    conceded["pts_to_pos_6"] = g["pts_to_pos"].transform(
        lambda s: s.rolling(6, min_periods=3).mean()
    )
    conceded = conceded.sort_values("kickoff_time")

    order = df.index
    left = (
        df[["opponent_team_code", "position", "kickoff_time"]]
        .reset_index()
        .dropna(subset=["kickoff_time", "opponent_team_code"])
        .sort_values("kickoff_time")
    )
    merged = pd.merge_asof(
        left,
        conceded[["opponent_team_code", "position", "kickoff_time", "pts_to_pos_6"]],
        on="kickoff_time",
        by=["opponent_team_code", "position"],
        direction="backward",
        allow_exact_matches=False,
    ).set_index("index")
    df["opp_pts_to_pos_6"] = merged["pts_to_pos_6"].reindex(order)
    return df


def add(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    df = _asof_elo(df, ctx, "team_code", "own_elo")
    df = _asof_elo(df, ctx, "opponent_team_code", "opp_elo")
    df["elo_diff"] = df["own_elo"] - df["opp_elo"]
    df = _team_defence(df, ctx)
    df = _pts_to_position(df)

    # player's career record vs this specific opponent (requires player-time sort)
    g = df.groupby(["player_code", "opponent_team_code"], sort=False)
    df["vs_opp_ppg"] = g["total_points"].transform(
        lambda s: s.shift(1).expanding(min_periods=1).mean()
    )
    df["vs_opp_games"] = g.cumcount()
    return df
