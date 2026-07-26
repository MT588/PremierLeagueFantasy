from collections import Counter

from optimizer.ilp import MAX_PER_CLUB, SQUAD_BY_POSITION, Candidate, optimize


def make_pool(n_teams: int = 20) -> list[Candidate]:
    """Synthetic pool: 3 GK + 6 DEF + 6 MID + 4 FWD per team code bucket spread."""
    pool = []
    code = 0
    for pos, per_team in ((1, 3), (2, 6), (3, 6), (4, 4)):
        for team in range(n_teams):
            for k in range(per_team):
                code += 1
                pool.append(
                    Candidate(
                        player_code=code,
                        position=pos,
                        team_code=team,
                        cost=40 + (code % 90),
                        predicted_points=(code * 7919 % 100) / 12,
                    )
                )
    return pool


def test_respects_all_fpl_rules():
    pool = make_pool()
    team = optimize(pool, budget=1000)
    assert not team.infeasible
    assert len(team.squad) == 15
    assert len(team.starting_xi) == 11
    assert len(team.bench) == 4
    assert team.captain in team.starting_xi
    assert team.total_cost <= 1000

    by_pos = Counter(team.players[c].position for c in team.squad)
    assert by_pos == SQUAD_BY_POSITION

    xi_pos = Counter(team.players[c].position for c in team.starting_xi)
    assert xi_pos[1] == 1 and xi_pos[2] >= 3 and xi_pos[4] >= 1

    by_club = Counter(team.players[c].team_code for c in team.squad)
    assert max(by_club.values()) <= MAX_PER_CLUB


def test_club_limit_binds():
    pool = make_pool()
    # make one club's players irresistible: without the club rule they'd all be picked
    stacked = [
        Candidate(c.player_code, c.position, 0, c.cost, 99.0)
        if c.team_code == 5 and c.position in (2, 3)
        else c
        for c in pool
    ]
    for c in stacked[:12]:
        if c.team_code == 0:
            c.predicted_points = 99.0
    team = optimize(stacked, budget=2000)
    by_club = Counter(team.players[c].team_code for c in team.squad)
    assert max(by_club.values()) <= MAX_PER_CLUB


def test_budget_binds():
    pool = make_pool()
    cheap = optimize(pool, budget=700)
    rich = optimize(pool, budget=1200)
    assert not cheap.infeasible and not rich.infeasible
    assert cheap.total_cost <= 700
    assert rich.expected_points >= cheap.expected_points


def test_captain_is_best_starter():
    pool = make_pool()
    team = optimize(pool)
    best_xi_points = max(team.players[c].predicted_points for c in team.starting_xi)
    assert team.players[team.captain].predicted_points == best_xi_points


def test_infeasible_budget():
    pool = make_pool()
    team = optimize(pool, budget=100)  # cannot afford any legal squad
    assert team.infeasible
