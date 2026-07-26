from fastapi import APIRouter
from sqlalchemy import text

from app import queries
from app.constants import MODEL_VERSION
from app.db import engine
from app.deps import current_season, next_gameweek
from app.schemas import Meta, TeamOut

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=Meta)
def meta() -> Meta:
    season_id, season_name = current_season()
    with engine.connect() as conn:
        pool = conn.execute(
            text("select count(*) from player_seasons where season_id = :s"),
            {"s": season_id},
        ).scalar()
        preds = conn.execute(
            text(
                "select count(*) from predictions where season_id = :s and model_version = :m"
            ),
            {"s": season_id, "m": MODEL_VERSION},
        ).scalar()
    return Meta(
        season=season_name,
        next_gameweek=next_gameweek(season_id),
        model_version=MODEL_VERSION,
        players_in_pool=pool,
        predictions=preds,
    )


@router.get("/teams", response_model=list[TeamOut])
def teams() -> list[TeamOut]:
    season_id, _ = current_season()
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(queries.TEAMS_LIST),
                {"season_id": season_id, "gameweek": next_gameweek(season_id)},
            )
            .mappings()
            .all()
        )
    return [TeamOut(**r) for r in rows]
