"""Leakage-safe feature engineering shared by training and inference.

Every rolling feature is computed over rows strictly BEFORE the target row
(shift(1) then roll), grouped by the stable cross-season player_code so form
carries across season boundaries. Inference rows are appended as stubs with
NaN stats; their features come from the trailing real rows, which also gives
the pre-season fallback (end-of-last-season form) for free.
"""

import pandas as pd
from sqlalchemy import Engine, text

HISTORY_SQL = """
select
  g.season_id, s.name as season_name, s.start_year, g.player_code, g.gameweek,
  g.fpl_fixture_id, g.was_home, g.minutes, g.total_points, g.goals_scored,
  g.assists, g.bonus, g.bps, g.ict_index,
  g.expected_goals, g.expected_assists, g.expected_goal_involvements,
  g.value, ps.position, ps.team_code, f.kickoff_time,
  case when g.was_home then f.home_difficulty else f.away_difficulty end as fdr,
  case when g.was_home then own.strength_attack_home else own.strength_attack_away end as own_attack,
  case when g.was_home then own.strength_overall_home else own.strength_overall_away end as own_overall,
  case when g.was_home then opp.strength_defence_away else opp.strength_defence_home end as opp_defence,
  case when g.was_home then opp.strength_overall_away else opp.strength_overall_home end as opp_overall
from player_gameweeks g
join seasons s on s.id = g.season_id
join player_seasons ps on ps.season_id = g.season_id and ps.player_code = g.player_code
left join fixtures f on f.season_id = g.season_id and f.fpl_fixture_id = g.fpl_fixture_id
left join team_seasons own on own.season_id = g.season_id and own.team_code = ps.team_code
left join team_seasons opp on opp.season_id = g.season_id and opp.team_code = g.opponent_team_code
"""

INFERENCE_FIXTURES_SQL = """
select f.gameweek, f.fpl_fixture_id, f.kickoff_time,
       f.home_team_code, f.away_team_code, f.home_difficulty, f.away_difficulty
from fixtures f
where f.season_id = :season_id and f.gameweek = any(:gameweeks) and not f.finished
"""

CURRENT_POOL_SQL = """
select ps.player_code, ps.position, ps.team_code, ps.now_cost, ps.status,
       ps.chance_of_playing, ps.fpl_element_id, p.web_name
from player_seasons ps
join players p on p.code = ps.player_code
where ps.season_id = :season_id
"""

ROLL_WINDOWS = (3, 5, 10)

FEATURES = [
    # rolling form
    *[f"points_avg_{w}" for w in ROLL_WINDOWS],
    *[f"minutes_avg_{w}" for w in ROLL_WINDOWS],
    "goals_sum_5", "assists_sum_5", "bonus_avg_5", "bps_avg_5", "ict_avg_5",
    # per-90 expected rates
    "xg90_5", "xa90_5", "xgi90_5", "xgi90_10",
    # availability / continuity / class
    "started_last", "new_season", "season_ppg", "prev_season_ppg",
    # fixture context
    "was_home_i", "fdr", "own_attack", "own_overall", "opp_defence", "opp_overall",
    # meta
    "position", "value",
]

TARGET = "total_points"


def load_history(engine: Engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(HISTORY_SQL), conn)
    return df


def _sort(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["player_code", "start_year", "gameweek", "kickoff_time"]).reset_index(
        drop=True
    )


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """df = history rows, optionally with appended inference stubs (NaN stats)."""
    df = _sort(df)
    g = df.groupby("player_code", sort=False)

    def lagged(col: str):
        return g[col].transform(lambda s: s.shift(1))

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

    # expected-stat rates per 90 (NaN-safe: 2021-22 has no xG data)
    for w in (5, 10):
        min_sum = g["minutes"].transform(lambda s, w=w: s.shift(1).rolling(w, min_periods=1).sum())
        for out, col in (
            (f"xg90_{w}", "expected_goals"),
            (f"xa90_{w}", "expected_assists"),
            (f"xgi90_{w}", "expected_goal_involvements"),
        ):
            stat_sum = g[col].transform(
                lambda s, w=w: s.shift(1).rolling(w, min_periods=1).sum()
            )
            df[out] = (stat_sum / min_sum.clip(lower=1)) * 90
    df = df.drop(columns=["xg90_10", "xa90_10"])

    df["started_last"] = (lagged("minutes") >= 60).astype(float)
    df["new_season"] = (
        g["season_id"].transform(lambda s: s.ne(s.shift(1))).astype(float)
    )
    # season points-per-game up to (not including) this row
    grp_season = df.groupby(["player_code", "season_id"], sort=False)
    cum_pts = grp_season["total_points"].transform(lambda s: s.shift(1).cumsum())
    cum_games = grp_season.cumcount().astype(float)
    df["season_ppg"] = cum_pts / cum_games.where(cum_games > 0)

    # previous season points-per-appearance: captures player class independent
    # of the last-few-games form window (critical for pre-season predictions)
    ppg = df.groupby(["player_code", "start_year"])["total_points"].agg(["sum", "count"])
    ppg_map = (ppg["sum"] / ppg["count"].clip(lower=1)).to_dict()
    df["prev_season_ppg"] = [
        ppg_map.get((c, y - 1)) for c, y in zip(df["player_code"], df["start_year"])
    ]

    df["was_home_i"] = df["was_home"].astype(float)
    df["position"] = df["position"].astype(int)
    return df


def build_training_frame(engine: Engine) -> pd.DataFrame:
    return add_features(load_history(engine))


def build_inference_frame(
    engine: Engine, season_id: int, gameweeks: list[int]
) -> pd.DataFrame:
    """History + one stub row per (current player, fixture in target gameweeks)."""
    history = load_history(engine)
    with engine.connect() as conn:
        fixtures = pd.read_sql(
            text(INFERENCE_FIXTURES_SQL),
            conn,
            params={"season_id": season_id, "gameweeks": gameweeks},
        )
        pool = pd.read_sql(text(CURRENT_POOL_SQL), conn, params={"season_id": season_id})
        start_year = conn.execute(
            text("select start_year from seasons where id = :sid"), {"sid": season_id}
        ).scalar_one()

    home = fixtures.rename(
        columns={"home_team_code": "team_code", "away_team_code": "opponent_team_code"}
    ).assign(was_home=True, fdr=fixtures["home_difficulty"])
    away = fixtures.rename(
        columns={"away_team_code": "team_code", "home_team_code": "opponent_team_code"}
    ).assign(was_home=False, fdr=fixtures["away_difficulty"])
    team_fixtures = pd.concat([home, away], ignore_index=True)[
        ["gameweek", "fpl_fixture_id", "kickoff_time", "team_code", "opponent_team_code",
         "was_home", "fdr"]
    ]

    stubs = pool.merge(team_fixtures, on="team_code", how="inner")
    stubs["season_id"] = season_id
    stubs["start_year"] = start_year
    stubs["value"] = stubs["now_cost"]

    with engine.connect() as conn:
        strengths = pd.read_sql(
            text("select * from team_seasons where season_id = :sid"),
            conn,
            params={"sid": season_id},
        )
    own = strengths.set_index("team_code")
    opp = strengths.set_index("team_code")
    stubs["own_attack"] = [
        own.at[t, "strength_attack_home" if h else "strength_attack_away"]
        for t, h in zip(stubs["team_code"], stubs["was_home"])
    ]
    stubs["own_overall"] = [
        own.at[t, "strength_overall_home" if h else "strength_overall_away"]
        for t, h in zip(stubs["team_code"], stubs["was_home"])
    ]
    stubs["opp_defence"] = [
        opp.at[t, "strength_defence_away" if h else "strength_defence_home"]
        for t, h in zip(stubs["opponent_team_code"], stubs["was_home"])
    ]
    stubs["opp_overall"] = [
        opp.at[t, "strength_overall_away" if h else "strength_overall_home"]
        for t, h in zip(stubs["opponent_team_code"], stubs["was_home"])
    ]
    stubs["is_inference"] = True
    history["is_inference"] = False

    combined = pd.concat([history, stubs], ignore_index=True)
    combined = add_features(combined)
    return combined[combined["is_inference"]].copy()
