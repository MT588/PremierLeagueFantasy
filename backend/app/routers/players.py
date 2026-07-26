from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app import queries
from app.db import engine
from app.deps import current_season, next_gameweek
from app.schemas import (
    FixtureOut,
    GameweekPoint,
    PlayerDetail,
    PlayerRow,
    PredictionOut,
)

router = APIRouter(tags=["players"])

SORTABLE = {
    "predicted_points",
    "price",
    "form",
    "xgi90",
    "total_points_last_season",
    "web_name",
}


@router.get("/players", response_model=list[PlayerRow])
def list_players(
    position: int | None = Query(None, ge=1, le=4),
    team: int | None = None,
    search: str | None = None,
    sort: str = "predicted_points",
    limit: int = Query(100, le=1000),
) -> list[PlayerRow]:
    if sort not in SORTABLE:
        raise HTTPException(400, f"sort must be one of {sorted(SORTABLE)}")
    season_id, _ = current_season()
    gw = next_gameweek(season_id)
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(queries.PLAYERS_LIST), {"season_id": season_id, "gameweek": gw}
            )
            .mappings()
            .all()
        )

    players = [dict(r) for r in rows]
    if position:
        players = [p for p in players if p["position"] == position]
    if team:
        players = [p for p in players if p["team_code"] == team]
    if search:
        s = search.lower()
        players = [
            p
            for p in players
            if s in p["web_name"].lower() or s in p["full_name"].lower()
        ]
    if sort == "web_name":
        players.sort(key=lambda p: p["web_name"].lower())
    else:
        players.sort(key=lambda p: (p[sort] is not None, p[sort] or 0), reverse=True)
    return [PlayerRow(**p) for p in players[:limit]]


@router.get("/players/{code}", response_model=PlayerDetail)
def player_detail(code: int) -> PlayerDetail:
    season_id, _ = current_season()
    with engine.connect() as conn:
        base = (
            conn.execute(
                text(
                    "select p.code, p.web_name, p.first_name || ' ' || p.second_name as full_name, "
                    "ps.position, ps.team_code, t.short_name as team_short, "
                    "ps.now_cost / 10.0 as price, ps.status "
                    "from players p "
                    "left join player_seasons ps on ps.player_code = p.code and ps.season_id = :sid "
                    "left join teams t on t.code = ps.team_code "
                    "where p.code = :code"
                ),
                {"code": code, "sid": season_id},
            )
            .mappings()
            .first()
        )
        if base is None:
            raise HTTPException(404, "unknown player code")
        history = (
            conn.execute(text(queries.PLAYER_HISTORY), {"code": code}).mappings().all()
        )
        upcoming = (
            conn.execute(
                text(queries.PLAYER_UPCOMING),
                {"season_id": season_id, "team_code": base["team_code"]},
            )
            .mappings()
            .all()
            if base["team_code"]
            else []
        )
        preds = (
            conn.execute(
                text(queries.PLAYER_PREDICTIONS), {"season_id": season_id, "code": code}
            )
            .mappings()
            .all()
        )

    return PlayerDetail(
        code=base["code"],
        web_name=base["web_name"],
        full_name=base["full_name"],
        position=base["position"] or 0,
        team_short=base["team_short"],
        price=float(base["price"] or 0),
        status=base["status"],
        history=[GameweekPoint(**h) for h in history],
        upcoming=[
            FixtureOut(
                gameweek=u["gameweek"],
                kickoff_time=u["kickoff_time"].isoformat()
                if u["kickoff_time"]
                else None,
                opponent_short=u["opponent_short"],
                was_home=u["was_home"],
                difficulty=u["difficulty"],
            )
            for u in upcoming
        ],
        predictions=[PredictionOut(**p) for p in preds],
    )
