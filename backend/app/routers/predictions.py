from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine
from app.deps import current_season, next_gameweek
from ml.train_v2 import MODEL_VERSION

router = APIRouter(tags=["predictions"])


@router.get("/predictions")
def list_predictions(
    gameweek: int | None = None,
    position: int | None = Query(None, ge=1, le=4),
    limit: int = Query(200, le=1000),
) -> list[dict]:
    season_id, _ = current_season()
    gw = gameweek or next_gameweek(season_id)
    sql = """
        select pr.player_code as code, p.web_name, ps.position,
               t.short_name as team_short, ps.now_cost / 10.0 as price,
               pr.gameweek, pr.predicted_points, pr.rating, pr.p_start
        from predictions pr
        join players p on p.code = pr.player_code
        join player_seasons ps on ps.season_id = pr.season_id and ps.player_code = pr.player_code
        left join teams t on t.code = ps.team_code
        where pr.season_id = :sid and pr.gameweek = :gw and pr.model_version = :mv
    """
    params: dict = {"sid": season_id, "gw": gw, "mv": MODEL_VERSION}
    if position:
        sql += " and ps.position = :pos"
        params["pos"] = position
    sql += " order by pr.predicted_points desc limit :limit"
    params["limit"] = limit
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]
