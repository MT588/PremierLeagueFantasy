from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app import queries
from app.constants import MODEL_VERSION
from app.db import engine
from app.deps import current_season, next_gameweek
from app.schemas import GameweekPlanOut, OptimalPlanOut, SquadPlayer, TransferPlayer
from optimizer.multi_period import (
    MultiCandidate,
    optimize_multi_period,
    prune_candidates,
)

router = APIRouter(tags=["team"])


@router.get("/optimal-team", response_model=OptimalPlanOut)
def optimal_team(
    budget: float = Query(100.0, ge=50, le=120, description="budget in millions"),
    horizon: int = Query(5, ge=1, le=10, description="gameweeks to plan over"),
) -> OptimalPlanOut:
    season_id, _ = current_season()
    gw = next_gameweek(season_id)
    if gw is None:
        raise HTTPException(503, "no upcoming gameweeks in the current season")
    gameweeks = list(range(gw, gw + horizon))

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(queries.OPTIMIZER_CANDIDATES_BY_GW),
                {
                    "season_id": season_id,
                    "gameweeks": gameweeks,
                    "model_version": MODEL_VERSION,
                },
            )
            .mappings()
            .all()
        )
    if not rows:
        raise HTTPException(503, "no predictions available — run ml.predict first")

    # Predictions are written a fixed number of gameweeks ahead, so a longer
    # horizon than the model has covered plans over what is actually there
    # rather than padding the tail with weeks worth nothing.
    gameweeks = sorted({r["gameweek"] for r in rows})

    candidates: dict[int, MultiCandidate] = {}
    names: dict[int, tuple[str, str | None]] = {}
    for r in rows:
        code = r["player_code"]
        candidate = candidates.get(code)
        if candidate is None:
            candidate = MultiCandidate(
                player_code=code,
                position=r["position"],
                team_code=r["team_code"],
                cost=r["cost"],
                predicted_points={},
            )
            candidates[code] = candidate
            names[code] = (r["web_name"], r["team_short"])
        candidate.predicted_points[r["gameweek"]] = float(r["predicted_points"])

    plan = optimize_multi_period(
        prune_candidates(list(candidates.values()), gameweeks),
        gameweeks,
        budget=int(budget * 10),
    )

    def squad_player(code: int, gameweek: int, captain: int) -> SquadPlayer:
        c = plan.players[code]
        return SquadPlayer(
            code=code,
            web_name=names[code][0],
            position=c.position,
            team_short=names[code][1],
            price=c.cost / 10.0,
            predicted_points=round(c.ev(gameweek), 2),
            is_captain=code == captain,
        )

    def transfer_player(code: int) -> TransferPlayer:
        c = candidates[code]
        return TransferPlayer(
            code=code,
            web_name=names[code][0],
            position=c.position,
            team_short=names[code][1],
            price=c.cost / 10.0,
        )

    return OptimalPlanOut(
        weeks=[
            GameweekPlanOut(
                gameweek=w.gameweek,
                starting_xi=[
                    squad_player(c, w.gameweek, w.captain) for c in w.starting_xi
                ],
                bench=[squad_player(c, w.gameweek, w.captain) for c in w.bench],
                transfers_in=[transfer_player(c) for c in w.transfers_in],
                transfers_out=[transfer_player(c) for c in w.transfers_out],
                bank_before=w.bank_before,
                bank_after=w.bank_after,
                transfers_used=w.transfers_used,
                expected_points=w.expected_points,
                total_cost=w.total_cost / 10.0,
            )
            for w in plan.weeks
        ],
        total_expected_points=plan.total_expected_points,
        budget=budget,
        horizon=len(gameweeks),  # what was planned, which may be short of the ask
        gameweeks=gameweeks,
        infeasible=plan.infeasible,
    )
