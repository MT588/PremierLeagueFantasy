"""Load curated CSVs (manager stints, European competitions) and backfill
set-piece duties + birth dates from cached FPL data. Idempotent."""

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from pipeline import fpl_api
from pipeline.ingest_vaastav import SEASONS, download_season, records
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

CURATED_DIR = Path(__file__).resolve().parent.parent / "data" / "curated"


def load_manager_stints(engine: Engine) -> None:
    df = pd.read_csv(CURATED_DIR / "manager_changes.csv")
    df["start_date"] = pd.to_datetime(df["start_date"]).dt.date
    df["end_date"] = pd.to_datetime(df["end_date"]).dt.date
    n = upsert(engine, "manager_stints", records(df), ["team_code", "start_date"])
    log.info("manager_stints: %d rows", n)


def load_european_competitions(engine: Engine) -> None:
    df = pd.read_csv(CURATED_DIR / "european_competitions.csv")
    with engine.connect() as conn:
        season_ids = dict(conn.execute(text("select name, id from seasons")).all())
    df["season_id"] = df["season_name"].map(season_ids)
    missing = df[df["season_id"].isna()]
    if len(missing):
        log.warning("skipping %d euro rows for unknown seasons", len(missing))
        df = df.dropna(subset=["season_id"])
    df = df[["season_id", "team_code", "competition"]]
    n = upsert(engine, "european_competitions", records(df), ["season_id", "team_code"])
    log.info("european_competitions: %d rows", n)


def backfill_setpiece_and_birthdate(engine: Engine) -> None:
    """Season-level set-piece orders from vaastav players_raw (historical) and
    the live bootstrap (current season); birth dates where available."""
    with engine.connect() as conn:
        season_ids = dict(conn.execute(text("select name, id from seasons")).all())

    for season in SEASONS:
        src = download_season(season)
        raw = pd.read_csv(src / "players_raw.csv")
        _apply_setpieces(engine, raw, season_ids[season], season)
        if "birth_date" in raw.columns:
            _apply_birthdates(engine, raw, season)

    data = fpl_api.bootstrap_static()
    elements = pd.DataFrame(data["elements"])
    current = max(season_ids.values())
    _apply_setpieces(engine, elements, current, "current")
    if "birth_date" in elements.columns:
        _apply_birthdates(engine, elements, "current")


def _apply_setpieces(
    engine: Engine, raw: pd.DataFrame, season_id: int, label: str
) -> None:
    cols = {
        "penalties_order": "penalties_order",
        "corners_and_indirect_freekicks_order": "corners_order",
        "direct_freekicks_order": "freekicks_order",
    }
    present = [c for c in cols if c in raw.columns]
    if not present:
        log.info("setpieces %s: no columns, skipping", label)
        return
    df = raw[["code", *present]].rename(columns={**cols, "code": "player_code"})
    df = df.drop_duplicates("player_code")
    df["season_id"] = season_id
    for target in cols.values():
        if target not in df.columns:
            df[target] = None
        df[target] = pd.to_numeric(df[target], errors="coerce")
    rows = records(df)
    with engine.begin() as conn:
        for i in range(0, len(rows), 500):
            conn.execute(
                text(
                    "update player_seasons set penalties_order = :penalties_order, "
                    "corners_order = :corners_order, freekicks_order = :freekicks_order "
                    "where season_id = :season_id and player_code = :player_code"
                ),
                rows[i : i + 500],
            )
    log.info("setpieces %s: %d players", label, len(rows))


def _apply_birthdates(engine: Engine, raw: pd.DataFrame, label: str) -> None:
    df = raw[["code", "birth_date"]].dropna().drop_duplicates("code")
    df["birth_date"] = pd.to_datetime(df["birth_date"], errors="coerce").dt.date
    df = df.dropna()
    rows = records(df.rename(columns={"code": "player_code"}))
    with engine.begin() as conn:
        for i in range(0, len(rows), 500):
            conn.execute(
                text(
                    "update players set birth_date = :birth_date where code = :player_code"
                ),
                rows[i : i + 500],
            )
    log.info("birth dates %s: %d players", label, len(rows))


def load_curated(engine: Engine) -> None:
    load_manager_stints(engine)
    load_european_competitions(engine)
    backfill_setpiece_and_birthdate(engine)
