"""Multi-gameweek FPL planner: one integer program over a rolling horizon.

Picks a squad for the first gameweek of the horizon, then plans the following
weeks: bench/XI substitutions and the captaincy are free and re-decided every
week, transfers are not. One free transfer accrues per gameweek and unused
transfers bank up to five, per the official rules; there are no points hits, so
a week can never spend more than it has banked.

Only the starting XI plus the captain double scores. The bench earns its place
purely through the weeks where it starts, and through the budget it leaves
behind for the rest of the squad.

A small bonus per banked transfer (`TRANSFER_BANK_BONUS`) makes the solver hold
transfers unless a move is worth more than the bonus, which batches moves into
later weeks rather than dribbling one out every gameweek. It is a tie-break on
the solver's preferences only: it never lands in the reported points.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import pulp

from optimizer.ilp import (
    MAX_PER_CLUB,
    SQUAD_BY_POSITION,
    XI_MAX_BY_POSITION,
    XI_MIN_BY_POSITION,
)

MAX_BANKED_TRANSFERS = 5
FREE_TRANSFERS_PER_GAMEWEEK = 1
TRANSFER_BANK_BONUS = 0.1
# A ten-gameweek plan is a much bigger program than a five. Keep this under the
# serverless maxDuration (60s, see docs/DEPLOYMENT.md) so a slow solve returns
# its best plan so far rather than having the request killed.
SOLVER_TIME_LIMIT = 45

# Pruning widths per position: 1 GK, 2 DEF, 3 MID, 4 FWD.
TOP_BY_TOTAL = {1: 8, 2: 28, 3: 28, 4: 22}
TOP_BY_PEAK = {1: 6, 2: 20, 3: 20, 4: 16}
CHEAPEST = {1: 4, 2: 8, 3: 8, 4: 6}


@dataclass
class MultiCandidate:
    player_code: int
    position: int  # 1 GK, 2 DEF, 3 MID, 4 FWD
    team_code: int
    cost: int  # 0.1m units
    predicted_points: dict[int, float]  # gameweek -> EV

    def ev(self, gameweek: int) -> float:
        return self.predicted_points.get(gameweek, 0.0)

    def total_ev(self, gameweeks: list[int]) -> float:
        return sum(self.ev(gw) for gw in gameweeks)

    def peak_ev(self, gameweeks: list[int]) -> float:
        return max((self.ev(gw) for gw in gameweeks), default=0.0)


@dataclass
class GameweekPlan:
    gameweek: int
    squad: list[int]  # 15 player codes
    starting_xi: list[int]  # 11 player codes
    bench: list[int]  # 4 codes, ordered by this week's predicted points desc
    captain: int
    transfers_in: list[int]  # ordered by position, pairs with transfers_out
    transfers_out: list[int]
    bank_before: int | None  # free transfers available; None when none can be made
    bank_after: int | None  # left over after this week, before next week's accrual
    transfers_used: int
    expected_points: float  # XI + captain double, this week only
    total_cost: int


@dataclass
class MultiPeriodPlan:
    weeks: list[GameweekPlan]
    total_expected_points: float
    infeasible: bool = False
    players: dict[int, MultiCandidate] = field(default_factory=dict)


def prune_candidates(
    candidates: list[MultiCandidate],
    gameweeks: list[int],
    top_total: dict[int, int] = TOP_BY_TOTAL,
    top_peak: dict[int, int] = TOP_BY_PEAK,
    cheapest: dict[int, int] = CHEAPEST,
) -> list[MultiCandidate]:
    """Cut the pool to a size CBC can chew through in seconds.

    Per position, keep the union of three rules: best total EV over the horizon
    (the season-long picks), best single-gameweek EV (a player with one huge
    opening fixture and nothing after would miss the total-EV cut, yet is
    exactly who a one-week transfer is for), and the cheapest few (bench fodder,
    and the guarantee that a legal 15 stays affordable).
    """
    by_position: dict[int, list[MultiCandidate]] = defaultdict(list)
    for c in candidates:
        by_position[c.position].append(c)

    kept: dict[int, MultiCandidate] = {}
    for pos, group in by_position.items():
        rules = (
            (lambda c: (-c.total_ev(gameweeks), c.player_code), top_total.get(pos, 0)),
            (lambda c: (-c.peak_ev(gameweeks), c.player_code), top_peak.get(pos, 0)),
            (lambda c: (c.cost, c.player_code), cheapest.get(pos, 0)),
        )
        for key, n in rules:
            for c in sorted(group, key=key)[:n]:
                kept[c.player_code] = c
    return sorted(kept.values(), key=lambda c: c.player_code)


def optimize_multi_period(
    candidates: list[MultiCandidate],
    gameweeks: list[int],
    budget: int = 1000,
    transfer_bonus: float = TRANSFER_BANK_BONUS,
    time_limit: int = SOLVER_TIME_LIMIT,
    initial_squad: list[int] | None = None,
    initial_bank: int = FREE_TRANSFERS_PER_GAMEWEEK,
) -> MultiPeriodPlan:
    """Plan a squad across `gameweeks`, transferring within the free allowance.

    With no `initial_squad` the first gameweek is a free pick and transfers
    start in the second week with one banked. Pass `initial_squad` (15 player
    codes, all of which must appear in `candidates`) to plan from an existing
    squad instead: the first week then costs transfers too, starting from
    `initial_bank`.
    """
    if not candidates or not gameweeks:
        return MultiPeriodPlan(weeks=[], total_expected_points=0.0, infeasible=True)

    idx = range(len(candidates))
    weeks = range(len(gameweeks))
    p = [[c.ev(gw) for gw in gameweeks] for c in candidates]

    # Weeks that can transfer. From scratch, week 0 is a free pick, so the first
    # opportunity is week 1; from an existing squad, week 0 already costs.
    from_scratch = initial_squad is None
    first_transfer_week = 1 if from_scratch else 0
    transfer_weeks = [t for t in weeks if t >= first_transfer_week]

    held = set(initial_squad or [])
    if held:
        known = {c.player_code for c in candidates}
        missing = held - known
        if missing:
            raise ValueError(
                f"initial_squad players missing from candidates: {sorted(missing)}"
            )

    clubs = {c.team_code for c in candidates}

    prob = pulp.LpProblem("fpl_multi_period", pulp.LpMaximize)
    squad = [
        [pulp.LpVariable(f"squad_{i}_{t}", cat="Binary") for t in weeks] for i in idx
    ]
    start = [
        [pulp.LpVariable(f"start_{i}_{t}", cat="Binary") for t in weeks] for i in idx
    ]
    capt = [
        [pulp.LpVariable(f"capt_{i}_{t}", cat="Binary") for t in weeks] for i in idx
    ]
    buy = {
        (i, t): pulp.LpVariable(f"buy_{i}_{t}", cat="Binary")
        for i in idx
        for t in transfer_weeks
    }
    sell = {
        (i, t): pulp.LpVariable(f"sell_{i}_{t}", cat="Binary")
        for i in idx
        for t in transfer_weeks
    }
    bank = {
        t: pulp.LpVariable(
            f"bank_{t}", lowBound=0, upBound=MAX_BANKED_TRANSFERS, cat="Integer"
        )
        for t in transfer_weeks
    }
    # What is left when the horizon runs out. Nothing after it scores, so
    # without this the last week's transfers would be free and the solver would
    # happily make pointless swaps that gain nothing.
    bank_out = (
        pulp.LpVariable(
            "bank_out", lowBound=0, upBound=MAX_BANKED_TRANSFERS, cat="Integer"
        )
        if transfer_weeks
        else None
    )

    banked = pulp.lpSum(bank[t] for t in transfer_weeks)
    if bank_out is not None:
        banked += bank_out
    prob += (
        pulp.lpSum((start[i][t] + capt[i][t]) * p[i][t] for i in idx for t in weeks)
        + transfer_bonus * banked
    )

    for t in weeks:
        prob += pulp.lpSum(squad[i][t] for i in idx) == 15
        prob += pulp.lpSum(start[i][t] for i in idx) == 11
        prob += pulp.lpSum(capt[i][t] for i in idx) == 1
        prob += pulp.lpSum(squad[i][t] * candidates[i].cost for i in idx) <= budget

        for pos, n in SQUAD_BY_POSITION.items():
            prob += (
                pulp.lpSum(squad[i][t] for i in idx if candidates[i].position == pos)
                == n
            )
            in_pos = pulp.lpSum(
                start[i][t] for i in idx if candidates[i].position == pos
            )
            prob += in_pos >= XI_MIN_BY_POSITION[pos]
            prob += in_pos <= XI_MAX_BY_POSITION[pos]

        for club in clubs:
            prob += (
                pulp.lpSum(squad[i][t] for i in idx if candidates[i].team_code == club)
                <= MAX_PER_CLUB
            )

        for i in idx:
            prob += start[i][t] <= squad[i][t]
            prob += capt[i][t] <= start[i][t]

    for t in transfer_weeks:
        for i in idx:
            previous = (
                (1 if candidates[i].player_code in held else 0)
                if t == 0
                else squad[i][t - 1]
            )
            prob += squad[i][t] == previous + buy[i, t] - sell[i, t]
            # Without this, buying and selling the same player in one week is
            # feasible: it changes nothing but burns a transfer.
            prob += buy[i, t] + sell[i, t] <= 1

        prob += pulp.lpSum(buy[i, t] for i in idx) <= bank[t]
        if t == first_transfer_week:
            prob += bank[t] == min(initial_bank, MAX_BANKED_TRANSFERS)
        else:
            # Upper bounds only: the bonus makes a bigger bank weakly better, so
            # every bank sits at its tight value in any optimal solution. The
            # variable's own upBound applies the five-transfer cap.
            prob += (
                bank[t]
                <= bank[t - 1]
                - pulp.lpSum(buy[i, t - 1] for i in idx)
                + FREE_TRANSFERS_PER_GAMEWEEK
            )

    if bank_out is not None:
        last = transfer_weeks[-1]
        prob += bank_out <= bank[last] - pulp.lpSum(buy[i, last] for i in idx)

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit))
    # A time-limited solve stops before proving optimality but still leaves a
    # usable incumbent, so trust the values rather than the status: only bail
    # when the solver came back with nothing to read.
    if pulp.LpStatus[status] == "Infeasible" or any(
        squad[i][t].value() is None for i in idx for t in weeks
    ):
        return MultiPeriodPlan(weeks=[], total_expected_points=0.0, infeasible=True)

    def chosen(var: pulp.LpVariable) -> bool:
        value = var.value()
        return value is not None and value > 0.5

    def by_position(i: int) -> tuple[int, int]:
        return candidates[i].position, candidates[i].player_code

    plan_weeks: list[GameweekPlan] = []
    used_players: dict[int, MultiCandidate] = {}
    for t in weeks:
        in_squad = [i for i in idx if chosen(squad[i][t])]
        xi = [i for i in in_squad if chosen(start[i][t])]
        bench = sorted(
            (i for i in in_squad if not chosen(start[i][t])),
            key=lambda i: p[i][t],
            reverse=True,
        )
        captain = next(i for i in xi if chosen(capt[i][t]))

        # Both lists are ordered by position, and each week's squad holds the
        # same shape, so transfers are position-for-position: pairing the lists
        # by index always pairs a like-for-like swap.
        transfers_in = sorted(
            (i for i in idx if t in bank and chosen(buy[i, t])), key=by_position
        )
        transfers_out = sorted(
            (i for i in idx if t in bank and chosen(sell[i, t])), key=by_position
        )

        available = round(bank[t].value()) if t in bank else None
        used = len(transfers_in)
        for i in in_squad:
            used_players[candidates[i].player_code] = candidates[i]

        plan_weeks.append(
            GameweekPlan(
                gameweek=gameweeks[t],
                squad=[candidates[i].player_code for i in in_squad],
                starting_xi=[candidates[i].player_code for i in xi],
                bench=[candidates[i].player_code for i in bench],
                captain=candidates[captain].player_code,
                transfers_in=[candidates[i].player_code for i in transfers_in],
                transfers_out=[candidates[i].player_code for i in transfers_out],
                bank_before=available,
                bank_after=None if available is None else available - used,
                transfers_used=used,
                expected_points=round(sum(p[i][t] for i in xi) + p[captain][t], 2),
                total_cost=sum(candidates[i].cost for i in in_squad),
            )
        )

    return MultiPeriodPlan(
        weeks=plan_weeks,
        total_expected_points=round(sum(w.expected_points for w in plan_weeks), 2),
        players=used_players,
    )
