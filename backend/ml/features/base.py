"""Base frame construction shared by training and inference.

History rows come from player_gameweeks joined with fixtures/team context;
inference rows are appended as stubs with NaN stats. Everything downstream
must be leakage-safe: only shift(1)/as-of-strictly-before aggregations.
"""

import pandas as pd
from sqlalchemy import Engine, text

HISTORY_SQL = """
select
  g.season_id, s.name as season_name, s.start_year, g.player_code, g.gameweek,
  g.fpl_fixture_id, g.was_home, g.minutes, g.total_points, g.goals_scored,
  g.assists, g.bonus, g.bps, g.ict_index,
  g.expected_goals, g.expected_assists, g.expected_goal_involvements,
  g.value, ps.position, ps.team_code, g.opponent_team_code, f.kickoff_time,
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
where ps.position between 1 and 4  -- excludes FPL's 2024-25 'assistant manager' elements
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
where ps.season_id = :season_id and ps.position between 1 and 4
"""


def load_history(engine: Engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(HISTORY_SQL), conn)
    df["kickoff_time"] = pd.to_datetime(df["kickoff_time"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    df["is_inference"] = False
    return df


def sort_player_time(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(
        ["player_code", "start_year", "gameweek", "kickoff_time"]
    ).reset_index(drop=True)


def build_stubs(engine: Engine, season_id: int, gameweeks: list[int]) -> pd.DataFrame:
    with engine.connect() as conn:
        fixtures = pd.read_sql(
            text(INFERENCE_FIXTURES_SQL),
            conn,
            params={"season_id": season_id, "gameweeks": gameweeks},
        )
        pool = pd.read_sql(
            text(CURRENT_POOL_SQL), conn, params={"season_id": season_id}
        )
        start_year = conn.execute(
            text("select start_year from seasons where id = :sid"), {"sid": season_id}
        ).scalar_one()
        season_name = conn.execute(
            text("select name from seasons where id = :sid"), {"sid": season_id}
        ).scalar_one()
        strengths = pd.read_sql(
            text("select * from team_seasons where season_id = :sid"),
            conn,
            params={"sid": season_id},
        )

    home = fixtures.rename(
        columns={"home_team_code": "team_code", "away_team_code": "opponent_team_code"}
    ).assign(was_home=True, fdr=fixtures["home_difficulty"])
    away = fixtures.rename(
        columns={"away_team_code": "team_code", "home_team_code": "opponent_team_code"}
    ).assign(was_home=False, fdr=fixtures["away_difficulty"])
    team_fixtures = pd.concat([home, away], ignore_index=True)[
        [
            "gameweek",
            "fpl_fixture_id",
            "kickoff_time",
            "team_code",
            "opponent_team_code",
            "was_home",
            "fdr",
        ]
    ]

    stubs = pool.merge(team_fixtures, on="team_code", how="inner")
    stubs["season_id"] = season_id
    stubs["season_name"] = season_name
    stubs["start_year"] = start_year
    stubs["value"] = stubs["now_cost"]
    stubs["kickoff_time"] = pd.to_datetime(stubs["kickoff_time"], utc=True).astype(
        "datetime64[ns, UTC]"
    )

    own = strengths.set_index("team_code")
    stubs["own_attack"] = [
        own.at[t, "strength_attack_home" if h else "strength_attack_away"]
        for t, h in zip(stubs["team_code"], stubs["was_home"])
    ]
    stubs["own_overall"] = [
        own.at[t, "strength_overall_home" if h else "strength_overall_away"]
        for t, h in zip(stubs["team_code"], stubs["was_home"])
    ]
    stubs["opp_defence"] = [
        own.at[t, "strength_defence_away" if h else "strength_defence_home"]
        for t, h in zip(stubs["opponent_team_code"], stubs["was_home"])
    ]
    stubs["opp_overall"] = [
        own.at[t, "strength_overall_away" if h else "strength_overall_home"]
        for t, h in zip(stubs["opponent_team_code"], stubs["was_home"])
    ]
    stubs["is_inference"] = True
    return stubs
