"""Manager-change features for both clubs in the fixture."""

import pandas as pd

from ml.features.context import FeatureContext

FEATURES = [
    "days_since_mgr_change_own",
    "new_mgr_own",
    "days_since_mgr_change_opp",
    "new_mgr_opp",
]

NEW_MANAGER_DAYS = 35  # roughly the first five matches


def _asof_stint(
    df: pd.DataFrame, ctx: FeatureContext, team_col: str, prefix: str
) -> pd.DataFrame:
    stints = ctx.manager_stints.rename(
        columns={"team_code": team_col, "start_date": "kickoff_time"}
    ).sort_values("kickoff_time")
    order = df.index
    left = (
        df[[team_col, "kickoff_time"]]
        .reset_index()
        .dropna(subset=["kickoff_time", team_col])
        .sort_values("kickoff_time")
    )
    merged = pd.merge_asof(
        left,
        stints.assign(stint_start=stints["kickoff_time"]),
        on="kickoff_time",
        by=team_col,
        direction="backward",
    ).set_index("index")
    days = (merged["kickoff_time"] - merged["stint_start"]).dt.days.reindex(order)
    df[f"days_since_mgr_change_{prefix}"] = days.clip(upper=1500)
    df[f"new_mgr_{prefix}"] = (days <= NEW_MANAGER_DAYS).astype(float)
    return df


def add(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    df = _asof_stint(df, ctx, "team_code", "own")
    df = _asof_stint(df, ctx, "opponent_team_code", "opp")
    return df
