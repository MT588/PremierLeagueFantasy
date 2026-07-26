"""Ingest historical seasons from the vaastav/Fantasy-Premier-League CSV archive.

Per-season FPL element ids are mapped to the stable cross-season `code`
via players_raw.csv; team ids are mapped to team `code` via teams.csv.
Column sets drift across seasons (xG columns exist from 2022-23 onward),
so every optional column falls back to NULL.
"""

import logging
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import Engine, select

from app.db import get_table
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

RAW_BASE = (
    "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
)
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
SEASON_FILES = ["players_raw.csv", "teams.csv", "fixtures.csv", "gws/merged_gw.csv"]

# player_gameweeks column -> merged_gw column (identical unless noted)
PGW_COLUMNS = {
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
    # 2025-26 onward only (the defensive-contribution rule's inputs)
    "tackles": "tackles",
    "clearances_blocks_interceptions": "clearances_blocks_interceptions",
    "recoveries": "recoveries",
}


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dicts with numpy scalars converted and NaN/NaT -> None."""
    out = []
    for row in df.to_dict("records"):
        r = {}
        for k, v in row.items():
            if pd.isna(v):
                r[k] = None
            elif hasattr(v, "item"):
                r[k] = v.item()
            else:
                r[k] = v
        out.append(r)
    return out


def download_season(season: str) -> Path:
    dest_dir = DATA_DIR / season
    for rel in SEASON_FILES:
        dest = dest_dir / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"{RAW_BASE}/{season}/{rel}"
        log.info("downloading %s", url)
        resp = httpx.get(url, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest_dir


def get_season_id(engine: Engine, season: str) -> int:
    start_year = int(season[:4])
    upsert(engine, "seasons", [{"name": season, "start_year": start_year}], ["name"])
    seasons = get_table("seasons")
    with engine.connect() as conn:
        return conn.execute(
            select(seasons.c.id).where(seasons.c.name == season)
        ).scalar_one()


def ingest_season(engine: Engine, season: str) -> dict[str, int]:
    src = download_season(season)
    season_id = get_season_id(engine, season)
    counts: dict[str, int] = {}

    teams = pd.read_csv(src / "teams.csv")
    players_raw = pd.read_csv(src / "players_raw.csv")
    fixtures = pd.read_csv(src / "fixtures.csv")
    merged_gw = pd.read_csv(src / "gws" / "merged_gw.csv", low_memory=False)

    # --- teams + team_seasons ---
    counts["teams"] = upsert(
        engine,
        "teams",
        records(teams[["code", "name", "short_name"]].drop_duplicates("code")),
        ["code"],
    )
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
    counts["team_seasons"] = upsert(
        engine, "team_seasons", records(ts), ["season_id", "team_code"]
    )

    team_id_to_code = dict(zip(teams["id"], teams["code"]))

    # --- players + player_seasons ---
    p = players_raw.drop_duplicates("code")
    counts["players"] = upsert(
        engine,
        "players",
        records(p[["code", "first_name", "second_name", "web_name"]]),
        ["code"],
    )
    ps = p[
        [
            "code",
            "id",
            "element_type",
            "team_code",
            "now_cost",
            "status",
            "chance_of_playing_next_round",
        ]
    ].rename(
        columns={
            "code": "player_code",
            "id": "fpl_element_id",
            "element_type": "position",
            "chance_of_playing_next_round": "chance_of_playing",
        }
    )
    ps["season_id"] = season_id
    counts["player_seasons"] = upsert(
        engine, "player_seasons", records(ps), ["season_id", "player_code"]
    )

    element_to_code = dict(zip(players_raw["id"], players_raw["code"]))

    # --- fixtures ---
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
    counts["fixtures"] = upsert(
        engine, "fixtures", records(fx), ["season_id", "fpl_fixture_id"]
    )

    # --- player_gameweeks ---
    gw = pd.DataFrame(
        {
            "season_id": season_id,
            "player_code": merged_gw["element"].map(element_to_code),
            "gameweek": merged_gw["GW"],
            "fpl_fixture_id": merged_gw["fixture"],
            "opponent_team_code": merged_gw["opponent_team"].map(team_id_to_code),
            "was_home": merged_gw["was_home"].astype(bool),
        }
    )
    for target, source in PGW_COLUMNS.items():
        gw[target] = merged_gw[source] if source in merged_gw.columns else None

    unmapped = gw["player_code"].isna().sum()
    if unmapped:
        log.warning("%s: dropping %d rows with unmapped element ids", season, unmapped)
        gw = gw.dropna(subset=["player_code"])
    gw = gw.drop_duplicates(
        subset=["season_id", "player_code", "gameweek", "fpl_fixture_id"]
    )
    counts["player_gameweeks"] = upsert(
        engine,
        "player_gameweeks",
        records(gw),
        ["season_id", "player_code", "gameweek", "fpl_fixture_id"],
    )

    log.info("%s ingested: %s", season, counts)
    return counts


def ingest_all(engine: Engine, seasons: list[str] | None = None) -> None:
    for season in seasons or SEASONS:
        ingest_season(engine, season)
