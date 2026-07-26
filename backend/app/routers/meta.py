from fastapi import APIRouter
from sqlalchemy import text

from app.db import engine
from app.deps import current_season, next_gameweek
from app.schemas import Meta, TeamOut
from ml.train_v2 import MODEL_VERSION

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}


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
        rows = conn.execute(
            text(
                "select t.code, t.name, t.short_name from team_seasons ts "
                "join teams t on t.code = ts.team_code "
                "where ts.season_id = :s order by t.name"
            ),
            {"s": season_id},
        ).all()
    return [TeamOut(code=r.code, name=r.name, short_name=r.short_name) for r in rows]
