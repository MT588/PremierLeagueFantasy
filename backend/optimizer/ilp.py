"""FPL squad optimizer: integer linear program over predicted points.

Maximizes starting XI points + captain double + lightly-weighted bench,
subject to the official squad rules: 15 players (2 GK / 5 DEF / 5 MID /
3 FWD), budget, max 3 per club, and a valid starting formation.
"""

from dataclasses import dataclass, field

import pulp

SQUAD_BY_POSITION = {1: 2, 2: 5, 3: 5, 4: 3}
XI_MIN_BY_POSITION = {1: 1, 2: 3, 3: 2, 4: 1}
XI_MAX_BY_POSITION = {1: 1, 2: 5, 3: 5, 4: 3}
BENCH_WEIGHT = 0.1
MAX_PER_CLUB = 3


@dataclass
class Candidate:
    player_code: int
    position: int  # 1 GK, 2 DEF, 3 MID, 4 FWD
    team_code: int
    cost: int  # 0.1m units
    predicted_points: float


@dataclass
class OptimalTeam:
    squad: list[int]  # 15 player codes
    starting_xi: list[int]  # 11 player codes
    captain: int
    bench: list[int]  # 4 codes, ordered by predicted points desc
    total_cost: int
    expected_points: float
    infeasible: bool = False
    players: dict[int, Candidate] = field(default_factory=dict)


def optimize(candidates: list[Candidate], budget: int = 1000) -> OptimalTeam:
    prob = pulp.LpProblem("fpl_squad", pulp.LpMaximize)
    idx = range(len(candidates))
    squad = [pulp.LpVariable(f"squad_{i}", cat="Binary") for i in idx]
    start = [pulp.LpVariable(f"start_{i}", cat="Binary") for i in idx]
    capt = [pulp.LpVariable(f"capt_{i}", cat="Binary") for i in idx]

    p = [c.predicted_points for c in candidates]
    prob += pulp.lpSum(
        start[i] * p[i] + capt[i] * p[i] + BENCH_WEIGHT * (squad[i] - start[i]) * p[i]
        for i in idx
    )

    prob += pulp.lpSum(squad) == 15
    prob += pulp.lpSum(start) == 11
    prob += pulp.lpSum(capt) == 1
    prob += pulp.lpSum(squad[i] * candidates[i].cost for i in idx) <= budget

    for pos, n in SQUAD_BY_POSITION.items():
        prob += pulp.lpSum(squad[i] for i in idx if candidates[i].position == pos) == n
    for pos in SQUAD_BY_POSITION:
        in_pos = pulp.lpSum(start[i] for i in idx if candidates[i].position == pos)
        prob += in_pos >= XI_MIN_BY_POSITION[pos]
        prob += in_pos <= XI_MAX_BY_POSITION[pos]

    clubs = {c.team_code for c in candidates}
    for club in clubs:
        prob += (
            pulp.lpSum(squad[i] for i in idx if candidates[i].team_code == club)
            <= MAX_PER_CLUB
        )

    for i in idx:
        prob += start[i] <= squad[i]
        prob += capt[i] <= start[i]

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        return OptimalTeam([], [], 0, [], 0, 0.0, infeasible=True)

    chosen = [i for i in idx if squad[i].value() > 0.5]
    xi = [i for i in chosen if start[i].value() > 0.5]
    bench = sorted(
        (i for i in chosen if i not in xi),
        key=lambda i: candidates[i].predicted_points,
        reverse=True,
    )
    captain = next(i for i in xi if capt[i].value() > 0.5)
    return OptimalTeam(
        squad=[candidates[i].player_code for i in chosen],
        starting_xi=[candidates[i].player_code for i in xi],
        captain=candidates[captain].player_code,
        bench=[candidates[i].player_code for i in bench],
        total_cost=sum(candidates[i].cost for i in chosen),
        expected_points=round(
            sum(candidates[i].predicted_points for i in xi)
            + candidates[captain].predicted_points,
            2,
        ),
        players={candidates[i].player_code: candidates[i] for i in chosen},
    )
