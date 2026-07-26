"""Fatigue and congestion: rest days, match density, European competition,
and international-tournament load with decay over the following gameweeks."""

import numpy as np
import pandas as pd

from ml.features.context import FeatureContext

FEATURES = [
    "days_since_club_match", "club_matches_14d", "club_matches_30d",
    "euro_comp", "gw_number",
    "intl_minutes_decayed", "intl_deep_run_decayed",
]

DECAY_GWS = 8
# minutes proxy per progress level when only squad membership is known
PROGRESS_MINUTES = {1: 180, 2: 270, 3: 340, 4: 420, 5: 500, 6: 580, 7: 580}


def _team_schedule(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    dates_by_team = {
        t: g["kickoff_time"].sort_values().to_numpy()
        for t, g in ctx.team_fixtures.groupby("team_code")
    }
    days_since = np.full(len(df), np.nan)
    m14 = np.full(len(df), np.nan)
    m30 = np.full(len(df), np.nan)
    kickoffs = df["kickoff_time"].to_numpy()
    teams = df["team_code"].to_numpy()
    for i in range(len(df)):
        dates = dates_by_team.get(teams[i])
        ts = kickoffs[i]
        if dates is None or pd.isna(ts):
            continue
        pos = np.searchsorted(dates, ts)
        if pos > 0:
            days_since[i] = (ts - dates[pos - 1]) / np.timedelta64(1, "D")
        m14[i] = pos - np.searchsorted(dates, ts - np.timedelta64(14, "D"))
        m30[i] = pos - np.searchsorted(dates, ts - np.timedelta64(30, "D"))
    df["days_since_club_match"] = np.clip(days_since, 0, 60)
    df["club_matches_14d"] = m14
    df["club_matches_30d"] = m30
    return df


def _intl_load(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    intl = ctx.intl.copy()
    intl["minutes_eff"] = [
        m if pd.notna(m) else PROGRESS_MINUTES.get(int(p) if pd.notna(p) else 1, 180)
        for m, p in zip(intl["minutes"], intl["team_progress"])
    ]
    summer = {}   # (player_code, season_start_year) -> (minutes_eff, progress)
    winter = {}   # WC2022: mid-season, decays from GW17 of 2022-23
    for r in intl.itertuples():
        if r.tournament == "WC" and r.year == 2022:
            winter[(r.player_code, 2022)] = (r.minutes_eff, r.team_progress or 1)
        else:
            summer[(r.player_code, r.year)] = (r.minutes_eff, r.team_progress or 1)

    minutes_out = np.zeros(len(df))
    deep_out = np.zeros(len(df))
    for i, (code, year, gw) in enumerate(
        zip(df["player_code"], df["start_year"], df["gameweek"])
    ):
        if pd.isna(gw):
            continue
        if (code, year) in summer:
            factor = max(0.0, 1 - (gw - 1) / DECAY_GWS)
            if factor > 0:
                m, p = summer[(code, year)]
                minutes_out[i] = m * factor
                deep_out[i] = p * factor
        if (code, year) in winter:
            factor = max(0.0, 1 - (gw - 17) / DECAY_GWS) if gw >= 17 else 0.0
            if factor > 0:
                m, p = winter[(code, year)]
                minutes_out[i] = max(minutes_out[i], m * factor)
                deep_out[i] = max(deep_out[i], p * factor)
    df["intl_minutes_decayed"] = minutes_out
    df["intl_deep_run_decayed"] = deep_out
    return df


def add(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    df = _team_schedule(df, ctx)
    df["euro_comp"] = [
        ctx.euro.get((sid, tc), 0) for sid, tc in zip(df["season_id"], df["team_code"])
    ]
    df["gw_number"] = df["gameweek"]
    df = _intl_load(df, ctx)
    return df
