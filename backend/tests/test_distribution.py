"""The Monte-Carlo points distribution and its closed-form cross-check.

`ev` (analytic) is what gets stored and ranked; `ev_mc` (the sampled mean) is
what the simulator actually produces. They compute the same quantity by
different routes, so a gap between them means the scoring arithmetic and the
sampler have drifted apart — which is the cheapest available catch for a
scaling mistake in either.

The agreement test is the point of this file. It is written against a synthetic
bundle rather than a trained model so it runs offline in seconds and so the
inputs can be pushed into the corners (keepers who face five shots a game,
substitutes who play twelve minutes) where the step-function components break.

It has already earned its keep: the analytic saves and goals-conceded terms were
being evaluated at the unconditional mean exposure and then multiplied by
P(play) a second time, which underpriced every keeper by about 0.12 points.
"""

import numpy as np
import pandas as pd
import pytest

from ml import scoring
from ml.components.bonus import BonusModel
from ml.distribution import Bundle, MinutesPool, simulate

N = 400
DRAWS = 6000


def _bonus_model() -> BonusModel:
    """A plausible P(bonus | rank bucket, returns): better buckets and bigger
    returns pay more. The boosters are never touched by the simulator."""
    distribution = {}
    for bucket in range(1, 9):
        for returns in range(3):
            strength = max(0.0, (5 - bucket) / 8) + 0.25 * returns
            p3 = min(0.5, strength)
            p1 = min(0.3, strength * 0.8)
            p0 = max(0.05, 1.0 - p3 - p1)
            total = p0 + p1 + p3
            distribution[(bucket, returns)] = {
                0: p0 / total,
                1: p1 / total,
                3: p3 / total,
            }
    return BonusModel(
        bps_model=None,
        direct_model=None,
        best_iteration_bps=0,
        best_iteration_direct=0,
        source="bps",
        rank_distribution=distribution,
    )


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    rng = np.random.default_rng(7)
    position = np.tile([1, 2, 3, 4], N // 4)
    return Bundle(
        position=position,
        minutes_probs=rng.dirichlet([1.5, 1.0, 4.0], size=N),
        goals_rate=np.where(position >= 3, rng.uniform(0.05, 0.8, N), rng.uniform(0.0, 0.08, N)),
        assists_rate=rng.uniform(0.02, 0.4, N),
        saves_rate=np.where(position == 1, rng.uniform(1.5, 5.0, N), 0.0),
        conceded_pmf=rng.dirichlet([6, 5, 3, 2, 1, 0.5, 0.3], size=N),
        p_dc=rng.uniform(0.05, 0.6, N),
        p_yellow=rng.uniform(0.02, 0.25, N),
        p_red=rng.uniform(0.0, 0.02, N),
        bonus_ranks=rng.integers(1, 9, N),
        bonus_model=_bonus_model(),
        scoring=scoring.for_season("2025-26"),
        minutes_pool=MinutesPool(
            cameo=np.array([8.0, 12.0, 20.0, 25.0, 33.0, 45.0, 55.0]),
            start=np.array([60.0, 70.0, 80.0, 90.0, 90.0, 90.0]),
        ),
    )


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_code": np.arange(N),
            "gameweek": 1,
            "fpl_fixture_id": 1,
            "season_id": 1,
        }
    )


@pytest.fixture(scope="module")
def simulated(bundle, frame) -> pd.DataFrame:
    return simulate(frame, bundle, draws=DRAWS, seed=1)


def test_analytic_ev_agrees_with_the_sampled_mean(simulated):
    """No systematic gap. The tolerances are Monte-Carlo error at these draws,
    not a bias allowance — the mean difference must sit around zero rather than
    merely be small."""
    difference = simulated["ev"] - simulated["ev_mc"]
    assert abs(difference.mean()) < 0.01, f"systematic bias: {difference.mean():+.4f}"
    assert difference.abs().mean() < 0.04
    assert difference.abs().max() < 0.25


def test_no_position_is_systematically_mispriced(simulated, bundle):
    """The bug this file caught was invisible in the pooled mean because only a
    quarter of the rows were keepers. Every position is checked on its own."""
    per_position = (
        simulated.assign(position=bundle.position)
        .groupby("position")
        .apply(lambda g: (g["ev"] - g["ev_mc"]).mean(), include_groups=False)
    )
    assert per_position.abs().max() < 0.02, per_position.to_dict()


def test_quantiles_are_ordered(simulated):
    assert (simulated["p10"] <= simulated["p50"]).all()
    assert (simulated["p50"] <= simulated["p90"]).all()


def test_probabilities_are_probabilities(simulated):
    for column in ("p_blank", "p_return", "p_haul"):
        assert simulated[column].between(0.0, 1.0).all()
    # a haul is a return, and a return is not a blank
    assert (simulated["p_haul"] <= simulated["p_return"] + 1e-12).all()
    assert (simulated["p_return"] + simulated["p_blank"] <= 1.0 + 1e-12).all()


def test_seeded_runs_are_identical(bundle, frame):
    a = simulate(frame, bundle, draws=1000, seed=42)
    b = simulate(frame, bundle, draws=1000, seed=42)
    pd.testing.assert_frame_equal(a, b)


def test_a_different_seed_moves_the_sample_but_not_the_closed_form(bundle, frame):
    a = simulate(frame, bundle, draws=1000, seed=1)
    b = simulate(frame, bundle, draws=1000, seed=2)
    assert not np.allclose(a["ev_mc"], b["ev_mc"])
    assert np.allclose(a["ev"], b["ev"])


def test_double_gameweek_sums_draws_not_quantiles(bundle, frame):
    """Two fixtures in one gameweek collapse to a single row whose draws were
    added before any statistic was taken. Expected points add exactly; the p90
    must come in *below* the sum of the two separate p90s, because both fixtures
    going right at once is rarer than either one doing so."""
    doubled = pd.concat(
        [frame.assign(fpl_fixture_id=1), frame.assign(fpl_fixture_id=2)],
        ignore_index=True,
    )
    double_bundle = bundle.slice(np.concatenate([np.arange(N), np.arange(N)]))

    combined = simulate(doubled, double_bundle, draws=DRAWS, seed=5)
    separate = simulate(
        doubled,
        double_bundle,
        draws=DRAWS,
        seed=5,
        group_keys=("player_code", "gameweek", "fpl_fixture_id"),
    )

    assert len(combined) == N
    assert len(separate) == 2 * N

    per_player = separate.groupby("player_code").agg(
        ev=("ev", "sum"), p90=("p90", "sum"), p_haul=("p_haul", "max")
    )
    merged = combined.set_index("player_code").join(per_player, rsuffix="_split")

    # expectation is additive
    assert np.allclose(merged["ev"], merged["ev_split"], atol=1e-9)
    # the tail is not: adding the two p90s claims both fixtures go right at once,
    # which is rarer than either doing so. (Not a per-row law — quantiles are not
    # subadditive in general, and these are integer-valued — so it is asserted
    # where it is actually a claim: on the aggregate and the clear majority.)
    assert merged["p90"].mean() < merged["p90_split"].mean()
    assert (merged["p90"] <= merged["p90_split"] + 1e-9).mean() > 0.95
    # and two fixtures give more haul chances than one
    assert (merged["p_haul"] >= merged["p_haul_split"] - 1e-9).mean() > 0.95


def test_more_draws_tighten_agreement(bundle, frame):
    """A sampling difference shrinks with draws; a bias does not. This is what
    separates the two, and is how the keeper mispricing was identified."""
    coarse = simulate(frame, bundle, draws=500, seed=3)
    fine = simulate(frame, bundle, draws=8000, seed=3)
    assert (fine["ev"] - fine["ev_mc"]).abs().mean() < (
        coarse["ev"] - coarse["ev_mc"]
    ).abs().mean()
