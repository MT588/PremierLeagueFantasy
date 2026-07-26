from fastapi import APIRouter
from sqlalchemy import text

from app import queries
from app.constants import MODEL_VERSION
from app.db import engine
from app.deps import current_season, next_gameweek
from app.schemas import PlayerStats

router = APIRouter(tags=["stats"])


@router.get("/player-stats", response_model=list[PlayerStats])
def player_stats() -> list[PlayerStats]:
    """Every current-pool player with form, season, ownership and fixture
    context. The dashboard fetches this once and filters client-side."""
    season_id, _ = current_season()
    gw = next_gameweek(season_id)
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(queries.PLAYER_STATS),
                {
                    "season_id": season_id,
                    "gameweek": gw,
                    "model_version": MODEL_VERSION,
                },
            )
            .mappings()
            .all()
        )
    return [PlayerStats(**r) for r in rows]
