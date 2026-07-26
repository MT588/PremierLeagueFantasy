from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app import queries
from app.db import engine
from app.deps import current_season, next_gameweek
from app.schemas import OptimalTeamOut, SquadPlayer
from optimizer.ilp import Candidate, optimize

router = APIRouter(tags=["team"])


@router.get("/optimal-team", response_model=OptimalTeamOut)
def optimal_team(
    budget: float = Query(100.0, ge=50, le=120, description="budget in millions"),
    horizon: int = Query(1, ge=1, le=5, description="gameweeks to optimize over"),
) -> OptimalTeamOut:
    season_id, _ = current_season()
    gw = next_gameweek(season_id)
    if gw is None:
        raise HTTPException(503, "no upcoming gameweeks in the current season")
    gameweeks = list(range(gw, gw + horizon))

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(queries.OPTIMIZER_CANDIDATES),
                {"season_id": season_id, "gameweeks": gameweeks},
            )
            .mappings()
            .all()
        )
    if not rows:
        raise HTTPException(503, "no predictions available — run ml.predict first")

    candidates = [
        Candidate(
            player_code=r["player_code"],
            position=r["position"],
            team_code=r["team_code"],
            cost=r["cost"],
            predicted_points=float(r["predicted_points"]),
        )
        for r in rows
    ]
    names = {r["player_code"]: (r["web_name"], r["team_short"]) for r in rows}

    result = optimize(candidates, budget=int(budget * 10))

    def to_out(code: int) -> SquadPlayer:
        c = result.players[code]
        return SquadPlayer(
            code=code,
            web_name=names[code][0],
            position=c.position,
            team_short=names[code][1],
            price=c.cost / 10.0,
            predicted_points=round(c.predicted_points, 2),
            is_captain=code == result.captain,
        )

    return OptimalTeamOut(
        starting_xi=[to_out(c) for c in result.starting_xi],
        bench=[to_out(c) for c in result.bench],
        total_cost=result.total_cost / 10.0,
        expected_points=result.expected_points,
        budget=budget,
        horizon=horizon,
        gameweeks=gameweeks,
        infeasible=result.infeasible,
    )
