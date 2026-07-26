"""Sync the current season from the official FPL API. Re-runnable weekly."""

import asyncio
import logging

import pandas as pd
from sqlalchemy import Engine, text, update

from app.db import get_table
from pipeline import fpl_api
from pipeline.ingest_vaastav import get_season_id, records
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

# player_gameweeks column -> element-summary history column
HISTORY_COLUMNS = {
    "minutes": "minutes",
    "total_points": "total_points",
    "goals_scored": "goals_scored",
    "assists": "assists",
    "clean_sheets": "clean_sheets",
    "goals_conceded": "goals_conceded",
    "saves": "saves",
    "bonus": "bonus",
    "bps": "bps",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
    "own_goals": "own_goals",
    "penalties_saved": "penalties_saved",
    "penalties_missed": "penalties_missed",
    "influence": "influence",
    "creativity": "creativity",
    "threat": "threat",
    "ict_index": "ict_index",
    "expected_goals": "expected_goals",
    "expected_assists": "expected_assists",
    "expected_goal_involvements": "expected_goal_involvements",
    "expected_goals_conceded": "expected_goals_conceded",
    "value": "value",
    "selected_by": "selected",
    "transfers_in": "transfers_in",
    "transfers_out": "transfers_out",
    "defensive_contribution": "defensive_contribution",
    "starts": "starts",
    "tackles": "tackles",
    "clearances_blocks_interceptions": "clearances_blocks_interceptions",
    "recoveries": "recoveries",
}


def season_name_from_bootstrap(data: dict) -> str:
    first_deadline = data["events"][0]["deadline_time"]  # e.g. '2026-08-21T17:30:00Z'
    start_year = int(first_deadline[:4])
    return f"{start_year}-{str(start_year + 1)[2:]}"


STRENGTH_COLS = [
    "strength_overall_home",
    "strength_overall_away",
    "strength_attack_home",
    "strength_attack_away",
    "strength_defence_home",
    "strength_defence_away",
]


def backfill_strengths(engine: Engine, season_id: int) -> None:
    """The FPL API serves zeroed team strength ratings pre-season. Backfill
    each zero from the team's most recent prior season, or the league
    average of the prior season for newly promoted teams."""
    with engine.begin() as conn:
        for col in STRENGTH_COLS:
            conn.execute(
                text(
                    f"""
                    update team_seasons ts set {col} = coalesce(
                      (select prev.{col} from team_seasons prev
                       where prev.team_code = ts.team_code
                         and prev.season_id < :sid and coalesce(prev.{col}, 0) > 0
                       order by prev.season_id desc limit 1),
                      (select avg(prev.{col})::smallint from team_seasons prev
                       where prev.season_id < :sid and coalesce(prev.{col}, 0) > 0)
                    )
                    where ts.season_id = :sid and coalesce(ts.{col}, 0) = 0
                    """
                ),
                {"sid": season_id},
            )


def sync_live(engine: Engine) -> None:
    data = fpl_api.bootstrap_static()
    season = season_name_from_bootstrap(data)
    season_id = get_season_id(engine, season)
    log.info("live sync: season %s (id %d)", season, season_id)

    seasons = get_table("seasons")
    with engine.begin() as conn:
        conn.execute(update(seasons).values(is_current=False))
        conn.execute(
            update(seasons).where(seasons.c.id == season_id).values(is_current=True)
        )

    # --- teams ---
    teams = pd.DataFrame(data["teams"])
    upsert(engine, "teams", records(teams[["code", "name", "short_name"]]), ["code"])
    ts = teams[
        [
            "code",
            "id",
            "strength_overall_home",
            "strength_overall_away",
            "strength_attack_home",
            "strength_attack_away",
            "strength_defence_home",
            "strength_defence_away",
        ]
    ].rename(columns={"code": "team_code", "id": "fpl_team_id"})
    ts["season_id"] = season_id
    upsert(engine, "team_seasons", records(ts), ["season_id", "team_code"])
    backfill_strengths(engine, season_id)
    team_id_to_code = dict(zip(teams["id"], teams["code"]))

    # --- players ---
    elements = pd.DataFrame(data["elements"]).drop_duplicates("code")
    upsert(
        engine,
        "players",
        records(elements[["code", "first_name", "second_name", "web_name"]]),
        ["code"],
    )
    ps = elements[
        [
            "code",
            "id",
            "element_type",
            "team_code",
            "now_cost",
            "status",
            "chance_of_playing_next_round",
            "selected_by_percent",
            "transfers_in_event",
            "transfers_out_event",
            "news",
        ]
    ].rename(
        columns={
            "code": "player_code",
            "id": "fpl_element_id",
            "element_type": "position",
            "chance_of_playing_next_round": "chance_of_playing",
        }
    )
    # FPL serves ownership as a string ("62.5"); the rest are already numeric.
    ps["selected_by_percent"] = pd.to_numeric(
        ps["selected_by_percent"], errors="coerce"
    )
    ps["season_id"] = season_id
    n_players = upsert(
        engine, "player_seasons", records(ps), ["season_id", "player_code"]
    )
    log.info("live sync: %d players in current pool", n_players)

    # --- fixtures ---
    fixtures = pd.DataFrame(fpl_api.fixtures())
    fx = pd.DataFrame(
        {
            "season_id": season_id,
            "fpl_fixture_id": fixtures["id"],
            "gameweek": fixtures["event"].astype("Int64"),
            "kickoff_time": pd.to_datetime(
                fixtures["kickoff_time"], utc=True, errors="coerce"
            ),
            "home_team_code": fixtures["team_h"].map(team_id_to_code),
            "away_team_code": fixtures["team_a"].map(team_id_to_code),
            "home_difficulty": fixtures["team_h_difficulty"],
            "away_difficulty": fixtures["team_a_difficulty"],
            "home_score": fixtures["team_h_score"].astype("Int64"),
            "away_score": fixtures["team_a_score"].astype("Int64"),
            "finished": fixtures["finished"].astype(bool),
        }
    )
    upsert(engine, "fixtures", records(fx), ["season_id", "fpl_fixture_id"])
    log.info("live sync: %d fixtures", len(fx))

    # --- per-gameweek history (no-op before the season starts) ---
    finished_gws = [e["id"] for e in data["events"] if e["finished"]]
    if not finished_gws:
        log.info("live sync: no finished gameweeks yet, skipping element summaries")
        return

    element_to_code = dict(zip(elements["id"], elements["code"]))
    summaries = asyncio.run(fpl_api.element_summaries(list(element_to_code)))
    rows = []
    for eid, summary in summaries.items():
        for h in summary.get("history", []):
            row = {
                "season_id": season_id,
                "player_code": element_to_code[eid],
                "gameweek": h["round"],
                "fpl_fixture_id": h["fixture"],
                "opponent_team_code": team_id_to_code.get(h["opponent_team"]),
                "was_home": h["was_home"],
            }
            for target, source in HISTORY_COLUMNS.items():
                row[target] = h.get(source)
            rows.append(row)
    n = upsert(
        engine,
        "player_gameweeks",
        rows,
        ["season_id", "player_code", "gameweek", "fpl_fixture_id"],
    )
    log.info("live sync: %d player-gameweek rows", n)
