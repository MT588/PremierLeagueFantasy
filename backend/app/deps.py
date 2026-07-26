from fastapi import HTTPException
from sqlalchemy import text

from app import queries
from app.db import engine


def current_season() -> tuple[int, str]:
    with engine.connect() as conn:
        row = conn.execute(text(queries.CURRENT_SEASON)).first()
    if row is None:
        raise HTTPException(503, "no current season loaded — run the pipeline first")
    return row.id, row.name


def next_gameweek(season_id: int) -> int | None:
    with engine.connect() as conn:
        return conn.execute(
            text(queries.NEXT_GAMEWEEK), {"season_id": season_id}
        ).scalar()
