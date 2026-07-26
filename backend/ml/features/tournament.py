"""Summer-tournament bridge: what a player did at the World Cup, and how late.

schedule.py already fades a squad-membership proxy over the opening gameweeks.
This group uses the richer per-player record the Wikipedia line-up loader
provides (minutes, starts, goals, the player's own last match date) and splits
the two effects a deep run has, which point in opposite directions:

  - fatigue and a late return -> rotation risk in GW1-4 (`tour_days_rest`,
    `tour_minutes_decayed`),
  - a player in form and nailed on for his country -> genuine attacking signal
    (`tour_goals90`, `tour_starts_share`).

Everything is zero for non-participants, and `tour_days_rest` is measured from
the player's own final tournament match, so a group-stage exit and a losing
finalist are distinguishable even within the same squad.
"""

import numpy as np
import pandas as pd

from ml.features.context import FeatureContext

FEATURES = [
    "tour_minutes_decayed",
    "tour_starts_share",
    "tour_goals90",
    "tour_matches",
    "tour_progress",
    "tour_days_rest",
    "tour_decay",
]

DECAY_GWS = 8  # matches schedule.DECAY_GWS
# A losing finalist gets ~33 days before GW1, a group-stage exit ~70. Cap well
# clear of that range so the ordering between them survives.
MAX_REST_DAYS = 90.0


def _tournament_index(ctx: FeatureContext) -> dict[tuple[int, int], dict]:
    """(player_code, affected season start year) -> tournament record.

    A summer tournament affects the season that starts the same year; the
    mid-season 2022 World Cup is handled by schedule.py's winter branch, which
    already fades it from GW17 of 2022-23.
    """
    intl = ctx.intl
    out: dict[tuple[int, int], dict] = {}
    for r in intl.itertuples():
        if r.tournament == "WC" and r.year == 2022:
            continue  # winter tournament: schedule.py owns it
        minutes = float(r.minutes) if pd.notna(r.minutes) else np.nan
        matches = float(r.matches) if pd.notna(r.matches) else np.nan
        out[(r.player_code, r.year)] = {
            "minutes": minutes,
            "matches": matches,
            "starts": float(r.starts) if pd.notna(getattr(r, "starts", None)) else np.nan,
            "goals": float(r.goals) if pd.notna(getattr(r, "goals", None)) else np.nan,
            "progress": float(r.team_progress) if pd.notna(r.team_progress) else 1.0,
            "last_match": getattr(r, "last_match_date", None),
        }
    return out


def add(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    records = _tournament_index(ctx)

    n = len(df)
    minutes = np.zeros(n)
    starts_share = np.zeros(n)
    goals90 = np.zeros(n)
    matches = np.zeros(n)
    progress = np.zeros(n)
    rest = np.full(n, np.nan)
    decay = np.zeros(n)

    kickoffs = df["kickoff_time"].to_numpy()
    for i, (code, year, gw) in enumerate(
        zip(df["player_code"], df["start_year"], df["gameweek"])
    ):
        record = records.get((code, year))
        if record is None or pd.isna(gw):
            continue
        factor = max(0.0, 1.0 - (gw - 1) / DECAY_GWS)
        decay[i] = factor
        progress[i] = record["progress"]
        played = record["minutes"]
        matches[i] = record["matches"] if not pd.isna(record["matches"]) else 0.0
        if not pd.isna(played):
            minutes[i] = played * factor
            if record["matches"] and not pd.isna(record["starts"]):
                starts_share[i] = record["starts"] / max(record["matches"], 1)
            if not pd.isna(record["goals"]) and played > 0:
                goals90[i] = record["goals"] / played * 90.0
        last = record["last_match"]
        if last is not None and not pd.isna(last) and not pd.isna(kickoffs[i]):
            days = (pd.Timestamp(kickoffs[i]) - pd.Timestamp(last, tz="UTC")).days
            rest[i] = min(max(float(days), 0.0), MAX_REST_DAYS)

    df["tour_minutes_decayed"] = minutes
    df["tour_starts_share"] = starts_share
    df["tour_goals90"] = goals90
    df["tour_matches"] = matches
    df["tour_progress"] = progress
    df["tour_days_rest"] = rest
    df["tour_decay"] = decay
    return df
