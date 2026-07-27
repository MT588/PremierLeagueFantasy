from collections import Counter

import pytest

from optimizer.ilp import MAX_PER_CLUB, SQUAD_BY_POSITION
from optimizer.multi_period import (
    MultiCandidate,
    optimize_multi_period,
    prune_candidates,
)

GAMEWEEKS = [1, 2, 3, 4, 5]


def make_multi_pool(
    n_teams: int = 6, gameweeks: list[int] = GAMEWEEKS, constant: bool = False
) -> list[MultiCandidate]:
    """Synthetic pool: 1 GK + 3 DEF + 3 MID + 2 FWD per club, EV varying by week.

    With `constant`, every player scores the same every week, so no transfer can
    ever pay for itself — the shape needed to watch transfers bank up.
    """
    pool = []
    code = 0
    for pos, per_team in ((1, 1), (2, 3), (3, 3), (4, 2)):
        for team in range(n_teams):
            for _ in range(per_team):
                code += 1
                base = (code * 7919 % 100) / 12
                pool.append(
                    MultiCandidate(
                        player_code=code,
                        position=pos,
                        team_code=team,
                        cost=40 + (code % 60),
                        predicted_points={
                            gw: base
                            if constant
                            else ((code * 7919 + gw * 104729) % 100) / 12
                            for gw in gameweeks
                        },
                    )
                )
    return pool


def make_fixed_fifteen(cost: int = 50) -> list[MultiCandidate]:
    """Exactly one legal squad — 2/5/5/3 spread over five clubs.

    Nothing to transfer to, so anything that changes between weeks has to be a
    substitution. Codes run 1-2 GK, 3-7 DEF, 8-12 MID, 13-15 FWD.
    """
    pool = []
    code = 0
    for pos, n, ev in ((1, 2, 5.0), (2, 5, 8.0), (3, 5, 10.0), (4, 3, 7.0)):
        for _ in range(n):
            code += 1
            pool.append(
                MultiCandidate(
                    player_code=code,
                    position=pos,
                    team_code=code % 5,
                    cost=cost,
                    predicted_points={gw: ev for gw in GAMEWEEKS},
                )
            )
    return pool


def assert_week_is_legal(week, plan, budget: int) -> None:
    assert len(week.squad) == 15
    assert len(week.starting_xi) == 11
    assert len(week.bench) == 4
    assert week.captain in week.starting_xi
    assert week.total_cost <= budget

    assert Counter(plan.players[c].position for c in week.squad) == SQUAD_BY_POSITION
    xi_pos = Counter(plan.players[c].position for c in week.starting_xi)
    assert xi_pos[1] == 1 and xi_pos[2] >= 3 and xi_pos[3] >= 2 and xi_pos[4] >= 1

    by_club = Counter(plan.players[c].team_code for c in week.squad)
    assert max(by_club.values()) <= MAX_PER_CLUB


def test_horizon_one_has_no_transfers():
    plan = optimize_multi_period(make_multi_pool(), [1], budget=1000)
    assert not plan.infeasible
    assert len(plan.weeks) == 1
    week = plan.weeks[0]
    assert_week_is_legal(week, plan, 1000)
    assert week.transfers_in == [] and week.transfers_out == []
    assert week.bank_before is None and week.bank_after is None
    assert plan.total_expected_points == week.expected_points


def test_weekly_rules_hold_across_the_horizon():
    plan = optimize_multi_period(make_multi_pool(), GAMEWEEKS, budget=1000)
    assert not plan.infeasible
    assert [w.gameweek for w in plan.weeks] == GAMEWEEKS
    for week in plan.weeks:
        assert_week_is_legal(week, plan, 1000)
    assert plan.total_expected_points == pytest.approx(
        sum(w.expected_points for w in plan.weeks), abs=0.01
    )


def test_unused_transfers_bank_up():
    plan = optimize_multi_period(make_multi_pool(constant=True), GAMEWEEKS, budget=1000)
    assert not plan.infeasible
    assert [w.bank_before for w in plan.weeks] == [None, 1, 2, 3, 4]
    assert sum(w.transfers_used for w in plan.weeks) == 0


def test_the_bank_stops_at_five():
    gameweeks = list(range(1, 8))
    pool = make_multi_pool(gameweeks=gameweeks, constant=True)
    plan = optimize_multi_period(pool, gameweeks, budget=1000)
    assert not plan.infeasible
    # Sixth and seventh weeks would hold 6 and 7 without the cap.
    assert [w.bank_before for w in plan.weeks] == [None, 1, 2, 3, 4, 5, 5]


def test_transfers_never_exceed_the_bank():
    plan = optimize_multi_period(make_multi_pool(), GAMEWEEKS, budget=1000)
    assert not plan.infeasible
    for week in plan.weeks:
        if week.bank_before is None:
            assert week.transfers_used == 0
        else:
            assert week.transfers_used <= week.bank_before
            assert week.bank_after == week.bank_before - week.transfers_used


def test_transfers_balance_by_position():
    plan = optimize_multi_period(make_multi_pool(), GAMEWEEKS, budget=1000)
    assert not plan.infeasible
    for week in plan.weeks:
        assert len(week.transfers_in) == len(week.transfers_out)
        # The frontend pairs the two lists by index, which only reads as a
        # like-for-like swap if they line up position by position.
        positions_in = [plan.players[c].position for c in week.transfers_in]
        positions_out = [plan.players[c].position for c in week.transfers_out]
        assert positions_in == positions_out


def test_transfers_wait_and_batch_rather_than_dribble_out():
    """Two upgrades that only pay from GW3 should both land in GW3, not earlier.

    Both are worthless in the first two weeks, so bringing either one in early
    buys nothing and burns a transfer that the bank bonus would rather keep.
    """
    pool = make_fixed_fifteen()
    for code in (101, 102):
        pool.append(
            MultiCandidate(
                player_code=code,
                position=3,
                team_code=code,
                cost=100,
                predicted_points={1: 0.0, 2: 0.0, 3: 50.0, 4: 50.0, 5: 50.0},
            )
        )
    plan = optimize_multi_period(pool, GAMEWEEKS, budget=900)

    assert not plan.infeasible
    assert [w.transfers_used for w in plan.weeks] == [0, 0, 2, 0, 0]
    assert set(plan.weeks[2].transfers_in) == {101, 102}
    assert plan.weeks[2].bank_before == 2 and plan.weeks[2].bank_after == 0
    assert all(code in plan.weeks[4].starting_xi for code in (101, 102))


def test_bench_and_xi_swap_for_free():
    """Two defenders trade places mid-horizon with no transfer available."""
    pool = make_fixed_fifteen()
    early, late = pool[2], pool[3]  # codes 3 and 4, both defenders
    early.predicted_points = {1: 9.0, 2: 9.0, 3: 0.0, 4: 0.0, 5: 0.0}
    late.predicted_points = {1: 0.0, 2: 0.0, 3: 9.0, 4: 9.0, 5: 9.0}

    plan = optimize_multi_period(pool, GAMEWEEKS, budget=800)

    assert not plan.infeasible
    assert sum(w.transfers_used for w in plan.weeks) == 0
    for week in plan.weeks[:2]:
        assert early.player_code in week.starting_xi
        assert late.player_code in week.bench
    for week in plan.weeks[2:]:
        assert late.player_code in week.starting_xi
        assert early.player_code in week.bench


def test_captain_changes_week_to_week():
    pool = make_fixed_fifteen()
    early, late = pool[7], pool[8]  # codes 8 and 9, both midfielders
    early.predicted_points = {1: 20.0, 2: 20.0, 3: 10.0, 4: 10.0, 5: 10.0}
    late.predicted_points = {1: 10.0, 2: 10.0, 3: 20.0, 4: 20.0, 5: 20.0}

    plan = optimize_multi_period(pool, GAMEWEEKS, budget=800)

    assert not plan.infeasible
    assert [w.captain for w in plan.weeks] == [early.player_code] * 2 + [
        late.player_code
    ] * 3


def test_expected_points_count_only_the_xi_and_captain():
    pool = make_fixed_fifteen()
    plan = optimize_multi_period(pool, [1], budget=800)
    week = plan.weeks[0]
    xi = sum(plan.players[c].ev(1) for c in week.starting_xi)
    assert week.expected_points == pytest.approx(
        xi + plan.players[week.captain].ev(1), abs=0.01
    )
    assert all(plan.players[c].ev(1) > 0 for c in week.bench)  # bench scores nothing


def test_infeasible_budget():
    plan = optimize_multi_period(make_multi_pool(), GAMEWEEKS, budget=100)
    assert plan.infeasible
    assert plan.weeks == []


def test_planning_from_an_existing_squad_spends_from_week_one():
    pool = make_fixed_fifteen()
    pool.append(
        MultiCandidate(
            player_code=101,
            position=3,
            team_code=101,
            cost=60,
            predicted_points={gw: 40.0 for gw in GAMEWEEKS},
        )
    )
    held = [c.player_code for c in pool if c.player_code != 101]

    plan = optimize_multi_period(
        pool, GAMEWEEKS, budget=800, initial_squad=held, initial_bank=1
    )

    assert not plan.infeasible
    assert plan.weeks[0].bank_before == 1
    assert plan.weeks[0].transfers_in == [101]
    assert len(plan.weeks[0].transfers_out) == 1


def test_initial_squad_must_be_in_the_candidate_pool():
    pool = make_fixed_fifteen()
    held = [c.player_code for c in pool[:14]] + [9999]
    with pytest.raises(ValueError, match="9999"):
        optimize_multi_period(pool, GAMEWEEKS, initial_squad=held)


def test_pruning_keeps_the_one_week_wonder():
    steady = [
        MultiCandidate(i, 3, i, 50, {gw: 10.0 for gw in GAMEWEEKS}) for i in range(1, 4)
    ]
    wonder = MultiCandidate(4, 3, 4, 50, {1: 30.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0})
    dud = MultiCandidate(5, 3, 5, 40, {gw: 1.0 for gw in GAMEWEEKS})

    kept = prune_candidates(
        [*steady, wonder, dud],
        GAMEWEEKS,
        top_total={3: 3},
        top_peak={3: 1},
        cheapest={3: 1},
    )
    codes = {c.player_code for c in kept}

    assert wonder.player_code in codes  # 30 in one week beats every steady peak
    assert dud.player_code in codes  # cheapest, kept as fodder
    assert codes == {1, 2, 3, 4, 5}


def test_pruning_cuts_the_pool_down():
    pool = make_multi_pool(n_teams=20)
    kept = prune_candidates(pool, GAMEWEEKS)
    assert len(kept) < len(pool)
    assert {c.position for c in kept} == {1, 2, 3, 4}
    # Enough of each position left to build a legal squad.
    counts = Counter(c.position for c in kept)
    assert all(counts[pos] >= n for pos, n in SQUAD_BY_POSITION.items())


def test_a_time_limited_solve_still_returns_something_usable():
    """CBC stops before proving optimality; the incumbent should still be read."""
    pool = make_multi_pool(n_teams=20)
    plan = optimize_multi_period(pool, GAMEWEEKS, budget=1000, time_limit=1)
    if not plan.infeasible:
        for week in plan.weeks:
            assert_week_is_legal(week, plan, 1000)
