"""v2 feature builder: named feature groups over a shared base frame.

Group order matters only in two places: the Understat 2021-22 xG backfill runs
before `form` (so xg90 windows benefit), and `market` runs after `opponent`
(it consumes own_elo/opp_elo). Everything is leakage-safe by construction —
shift(1) windows or as-of-strictly-before joins.
"""

import pandas as pd
from sqlalchemy import Engine, text

from ml.features import (
    career,
    context,
    form,
    form_eb,
    manager,
    market,
    meta,
    opponent,
    schedule,
    setpiece,
    tournament,
    understat_group,
)
from ml.features.base import build_stubs, load_history, sort_player_time

FEATURES_BY_GROUP: dict[str, list[str]] = {
    "form": form.FEATURES,
    "career": career.FEATURES,
    "understat": understat_group.FEATURES,
    "opponent": opponent.FEATURES,
    "market": market.FEATURES,
    "schedule": schedule.FEATURES,
    "manager": manager.FEATURES,
    "setpiece": setpiece.FEATURES,
    "meta": meta.FEATURES,
    # v3 additions
    "form_eb": form_eb.FEATURES,
    "tournament": tournament.FEATURES,
}

# Shipped feature set, selected by ablation on the 2025-26 fold (see
# ml/artifacts/ablation_v2.md): understat is the largest single win
# (-0.011 MAE), career helps rank correlation, setpiece is a small free win.
# opponent/market/schedule/manager added MAE noise and diluted rank quality
# for the POINTS model, so they are excluded here — but every group is still
# computed on the frame: the minutes model uses schedule+manager+meta, and
# ablation/re-selection can re-enable groups without code changes.
SELECTED_GROUPS: list[str] = ["form", "meta", "career", "understat", "setpiece"]

FEATURES: list[str] = [f for g in SELECTED_GROUPS for f in FEATURES_BY_GROUP[g]]

# v3 pool. The component models in ml/components/ draw from this and the
# ablation (ml/ablation_v3.py -> docs/ablation_v3.md) prunes it. Unlike v2's
# single regressor, a per-component model can use opponent/market/schedule
# context sensibly — a clean-sheet model wants exactly those — so nothing is
# excluded up front.
#
# `tournament` is computed but NOT shipped. Measured on the v2 architecture
# (ml/eval_form_fix.py -> docs/form_fix_v3.json) it moved nothing: the points
# stage got slightly worse on the one fold able to learn it (2025-26 GW1-8 MAE
# 1.0502 -> 1.0528) and the minutes stage moved by 3e-5. Only folds whose
# training seasons contain a summer tournament can learn the group at all,
# which today means a single fold — too little to ship on. The loader behind it
# still earns its place: international_load now holds exact parsed minutes,
# starts and goals instead of a squad-membership proxy, which feeds the
# `schedule` group's intl features.
SELECTED_GROUPS_V3: list[str] = [
    "form",
    "form_eb",
    "meta",
    "career",
    "understat",
    "setpiece",
    "opponent",
    "market",
    "schedule",
    "manager",
]

FEATURES_V3: list[str] = [f for g in SELECTED_GROUPS_V3 for f in FEATURES_BY_GROUP[g]]

TARGET = "total_points"

FEATURE_LABELS: dict[str, str] = {
    "points_avg_3": "Form — avg points, last 3",
    "points_avg_5": "Form — avg points, last 5",
    "points_avg_10": "Form — avg points, last 10",
    "minutes_avg_3": "Minutes — avg, last 3",
    "minutes_avg_5": "Minutes — avg, last 5",
    "minutes_avg_10": "Minutes — avg, last 10",
    "goals_sum_5": "Goals in last 5",
    "assists_sum_5": "Assists in last 5",
    "bonus_avg_5": "Bonus points — avg, last 5",
    "bps_avg_5": "Bonus system score — avg, last 5",
    "ict_avg_5": "ICT index — avg, last 5",
    "xg90_5": "Expected goals per 90, last 5",
    "xa90_5": "Expected assists per 90, last 5",
    "xgi90_5": "Expected goal involvements per 90, last 5",
    "xgi90_10": "Expected goal involvements per 90, last 10",
    "points_ewma_hl3": "Hot streak (fast form)",
    "points_ewma_hl8": "Sustained form (slow)",
    "xgi90_ewma_hl5": "Chance quality trend",
    "minutes_ewma_hl3": "Recent minutes trend",
    "season_ppg": "Points per game this season",
    "prev_season_ppg": "Points per game last season",
    "ppg_prev2": "Points per game, last 2 seasons",
    "ppg_prev3": "Points per game, last 3 seasons",
    "pts_per90_prev1": "Points per 90 last season",
    "minutes_share_prev1": "Share of minutes last season",
    "starts_prev1": "Starts last season",
    "seasons_in_pl": "Seasons of PL experience",
    "age_years": "Age",
    "ust_npxg90_5": "Non-penalty xG per 90, last 5 (Understat)",
    "ust_xa90_5": "xA per 90, last 5 (Understat)",
    "ust_shots90_5": "Shots per 90, last 5",
    "ust_kp90_5": "Key passes per 90, last 5",
    "ust_npxg90_20": "Shot quality, last 20 matches",
    "ust_career_npxg90_adj": "Career xG rate (league-adjusted)",
    "ust_career_xa90_adj": "Career xA rate (league-adjusted)",
    "ust_career_minutes_adj": "Career minutes (recent seasons)",
    "ust_prev_league_coef": "Previous league strength",
    "own_elo": "Team strength (Elo)",
    "opp_elo": "Opponent strength (Elo)",
    "elo_diff": "Strength gap vs opponent",
    "opp_goals_conceded_6": "Opponent goals conceded, last 6",
    "opp_cs_rate_10": "Opponent clean-sheet rate, last 10",
    "opp_pts_to_pos_6": "Points opponent concedes to this position",
    "vs_opp_ppg": "Career record vs this opponent",
    "vs_opp_games": "Games played vs this opponent",
    "p_win_elo": "Win probability",
    "p_draw_elo": "Draw probability",
    "p_loss_elo": "Loss probability",
    "days_since_club_match": "Days since last club match",
    "club_matches_14d": "Matches in last 14 days",
    "club_matches_30d": "Matches in last 30 days",
    "euro_comp": "European competition",
    "gw_number": "Gameweek number",
    "intl_minutes_decayed": "Summer tournament minutes (fading)",
    "intl_deep_run_decayed": "Deep tournament run (fading)",
    "days_since_mgr_change_own": "Days since manager change",
    "new_mgr_own": "New manager bounce window",
    "days_since_mgr_change_opp": "Opponent manager tenure",
    "new_mgr_opp": "Opponent has new manager",
    "pen_order": "Penalty-taker order",
    "is_pen_taker": "First-choice penalty taker",
    "corner_duty": "Corner-taking duty",
    "fk_duty": "Free-kick duty",
    "was_home_i": "Home fixture",
    "position": "Position",
    "value": "Price",
    "new_season": "First match of a new season",
    "started_last": "Started last match",
    "start_share_5": "Start rate, last 5",
    "start_share_10": "Start rate, last 10",
    "played_share_5": "Appearance rate, last 5",
    "fdr": "Fixture difficulty rating",
    "own_attack": "Team attack strength (FPL)",
    "own_overall": "Team overall strength (FPL)",
    "opp_defence": "Opponent defence strength (FPL)",
    "opp_overall": "Opponent overall strength (FPL)",
    "eb_points_pg": "Points per game (form blended with prior)",
    "eb_minutes": "Minutes per game (blended)",
    "eb_start_share": "Start rate (blended)",
    "eb_goals90": "Goals per 90 (blended)",
    "eb_assists90": "Assists per 90 (blended)",
    "eb_xg90": "Expected goals per 90 (blended)",
    "eb_xa90": "Expected assists per 90 (blended)",
    "eb_xgi90": "Expected involvements per 90 (blended)",
    "eb_bps": "Bonus system score per game (blended)",
    "eb_dc90": "Defensive actions per 90 (blended)",
    "games_played_season": "Games played this season",
    "minutes90_season": "90s played this season",
    "eb_weight_cur": "Weight on this season vs last",
    "is_new_to_club": "New club since last appearance",
    "tour_minutes_decayed": "Summer tournament minutes (fading)",
    "tour_starts_share": "Started share at the tournament",
    "tour_goals90": "Tournament goals per 90",
    "tour_matches": "Tournament matches played",
    "tour_progress": "How far his nation went",
    "tour_days_rest": "Days since his last tournament match",
    "tour_decay": "How recent the tournament is",
}


def _load_birth_dates(engine: Engine) -> pd.Series:
    with engine.connect() as conn:
        df = pd.read_sql(text("select code, birth_date from players"), conn)
    return df.set_index("code")["birth_date"]


def add_all_features(
    df: pd.DataFrame, ctx: context.FeatureContext, birth_dates: pd.Series
) -> pd.DataFrame:
    df = sort_player_time(df)
    df = understat_group.backfill_2021_xg(df, ctx)
    # row-order-dependent groups first (player-time sorted)
    df = form.add(df)
    df = meta.add(df)
    df = career.add(df, birth_dates)
    # as-of joins and lookups (restore their own ordering internally)
    df = opponent.add(df, ctx)
    df = market.add(df)
    df = schedule.add(df, ctx)
    df = manager.add(df, ctx)
    df = setpiece.add(df, ctx)
    df = understat_group.add(df, ctx)
    df = tournament.add(df, ctx)
    # last: its priors borrow the Understat career rates computed just above
    df = form_eb.add(df, ctx)
    return df


def build_training_frame(engine: Engine) -> pd.DataFrame:
    ctx = context.load_context(engine)
    df = load_history(engine)
    return add_all_features(df, ctx, _load_birth_dates(engine))


def build_inference_frame(
    engine: Engine, season_id: int, gameweeks: list[int]
) -> pd.DataFrame:
    ctx = context.load_context(engine)
    history = load_history(engine)
    stubs = build_stubs(engine, season_id, gameweeks)
    combined = pd.concat([history, stubs], ignore_index=True)
    combined = add_all_features(combined, ctx, _load_birth_dates(engine))
    return combined[combined["is_inference"]].copy()
