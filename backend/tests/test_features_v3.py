"""Leakage safety and shrinkage behaviour for the v3 feature pool.

The future-mutation test from test_features_v2.py, widened to the v3 pool and to
the component label columns that arrived with the 2025-26 defensive-contribution
rule. v3 feeds seven component models instead of one regressor, so a leak in a
column only one component reads would not show up in the v2 test at all.

The shrinkage tests cover the season-boundary fix, which is the part of v3 that
matters most in August: `k` must be fitted on training rows only, and a
gameweek-1 row — where the player has no current-season evidence — must fall
back to its prior rather than to whatever the rolling window happens to hold.
"""

import numpy as np
import pandas as pd
import pytest

from app.db import engine
from ml import shrinkage
from ml.features import FEATURES_V3, _load_birth_dates, add_all_features, form_eb
from ml.features.base import load_history
from ml.features.context import load_context

# v2's list plus every component label v3 learns from. A column that is not
# mutated here is a column this test cannot prove anything about.
MUTABLE_COLS = [
    "total_points",
    "minutes",
    "goals_scored",
    "assists",
    "bonus",
    "bps",
    "ict_index",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    # v3 component labels
    "clean_sheets",
    "goals_conceded",
    "saves",
    "yellow_cards",
    "red_cards",
    "own_goals",
    "defensive_contribution",
    "tackles",
    "clearances_blocks_interceptions",
    "recoveries",
]

CUTOFF = pd.Timestamp("2024-01-01", tz="UTC")


@pytest.fixture(scope="module")
def built():
    ctx = load_context(engine)
    birth = _load_birth_dates(engine)
    hist = load_history(engine)
    base = add_all_features(hist.copy(), ctx, birth)
    return ctx, birth, hist, base


def test_no_leakage_from_future_rows(built):
    """Mutating every stat after the cutoff must not move any v3 feature on any
    row at or before it."""
    ctx, birth, hist, base = built
    mutated_input = hist.copy()
    future = mutated_input["kickoff_time"] > CUTOFF
    assert future.sum() > 10_000
    for col in MUTABLE_COLS:
        if col in mutated_input.columns:
            mutated_input.loc[future, col] = mutated_input.loc[future, col] * 3 + 7

    mutated = add_all_features(mutated_input, ctx, birth)

    past = base["kickoff_time"] <= CUTOFF
    a = base.loc[past, FEATURES_V3].to_numpy(dtype=float)
    b = mutated.loc[past, FEATURES_V3].to_numpy(dtype=float)
    both_nan = np.isnan(a) & np.isnan(b)
    close = np.isclose(a, b, rtol=1e-9, atol=1e-9) | both_nan
    bad = np.argwhere(~close)
    assert close.all(), (
        f"{len(bad)} leaked cells; first offenders: "
        f"{[(FEATURES_V3[j], base.loc[past].iloc[i]['season_name']) for i, j in bad[:5]]}"
    )


def test_component_only_features_are_also_leakage_safe(built):
    """The defensive-contribution, discipline and saves features are consumed by
    single components and so are absent from FEATURES_V3 — they still have to be
    backward-looking."""
    ctx, birth, hist, base = built
    extra = [
        f
        for f in (
            form_eb.DC_FEATURES + form_eb.DISCIPLINE_FEATURES + form_eb.SAVES_FEATURES
        )
        if f in base.columns
    ]
    assert extra, "component feature lists resolved to nothing"

    mutated_input = hist.copy()
    future = mutated_input["kickoff_time"] > CUTOFF
    for col in MUTABLE_COLS:
        if col in mutated_input.columns:
            mutated_input.loc[future, col] = mutated_input.loc[future, col] * 3 + 7
    mutated = add_all_features(mutated_input, ctx, birth)

    past = base["kickoff_time"] <= CUTOFF
    a = base.loc[past, extra].to_numpy(dtype=float)
    b = mutated.loc[past, extra].to_numpy(dtype=float)
    both_nan = np.isnan(a) & np.isnan(b)
    assert (np.isclose(a, b, rtol=1e-9, atol=1e-9) | both_nan).all()


def test_shrinkage_k_is_fitted_only_on_the_rows_it_is_given(built):
    """`fit_ks` must be a pure function of its input frame. train_v3 hands it the
    fold's training seasons; if it reached anywhere else, a fold's weights would
    carry information from its own test season."""
    *_, base = built
    early = base[base["start_year"] <= 2022]
    late = base[base["start_year"] <= 2024]

    ks_early = shrinkage.fit_ks(early)
    ks_late = shrinkage.fit_ks(late)

    assert set(ks_early) == {s.name for s in form_eb.STATS}
    # repeated on the same rows it is deterministic
    assert shrinkage.fit_ks(early) == ks_early
    # and more seasons is a different problem, so at least one weight moves
    assert ks_early != ks_late


def test_gameweek_one_leans_on_the_prior(built):
    """The season-boundary fix in one assertion: with no current-season evidence
    the blend weight is zero, so the shrunk feature *is* the prior."""
    *_, base = built
    opener = base[(base["season_name"] == "2024-25") & (base["gameweek"] == 1)]
    assert len(opener) > 100

    assert np.allclose(opener["_eb_n_points_pg"].fillna(0.0), 0.0)
    assert np.allclose(opener["eb_weight_cur"].fillna(0.0), 0.0)

    prior = opener["_eb_prior_points_pg"]
    shrunk = opener["eb_points_pg"]
    both = prior.notna() & shrunk.notna()
    assert both.sum() > 100
    assert np.allclose(shrunk[both], prior[both])


def test_blend_weight_rises_with_evidence(built):
    """`w = n / (n + k)` — by mid-season the current campaign should carry most
    of the weight, which is the whole point of not hard-coding "last 5"."""
    *_, base = built
    season = base[base["season_name"] == "2024-25"]
    early = season[season["gameweek"] <= 2]["eb_weight_cur"].mean()
    late = season[season["gameweek"] >= 30]["eb_weight_cur"].mean()
    assert early < 0.25
    assert late > 0.75
    assert early < late


def test_apply_is_idempotent_and_k_actually_moves_the_blend(built):
    """`apply` is re-run per fold with fitted weights, so it must not depend on
    having been run before — and a bigger k must pull toward the prior."""
    *_, base = built
    rows = base[base["season_name"] == "2024-25"].head(5000).copy()

    once = form_eb.apply(rows.copy(), form_eb.DEFAULT_KS)
    twice = form_eb.apply(once.copy(), form_eb.DEFAULT_KS)
    assert np.allclose(
        once["eb_points_pg"].to_numpy(dtype=float),
        twice["eb_points_pg"].to_numpy(dtype=float),
        equal_nan=True,
    )

    heavy = form_eb.apply(rows.copy(), {**form_eb.DEFAULT_KS, "points_pg": 1000.0})
    prior = rows["_eb_prior_points_pg"]
    usable = prior.notna() & rows["_eb_cur_points_pg"].notna()
    assert usable.sum() > 500
    # a huge k means "trust the prior"
    assert np.abs(heavy.loc[usable, "eb_points_pg"] - prior[usable]).mean() < np.abs(
        once.loc[usable, "eb_points_pg"] - prior[usable]
    ).mean()


def test_fitted_ks_beat_or_match_the_documented_defaults(built):
    """fit_ks searches the default alongside the grid, so a fit can never come
    out worse than the fallback it replaces."""
    *_, base = built
    train = base[base["start_year"] <= 2023]
    played = train[train["minutes"].fillna(0) >= shrinkage.MIN_MINUTES]
    ks = shrinkage.fit_ks(train)

    for stat in form_eb.STATS:
        fitted_loss = shrinkage._loss_for(stat, played, ks[stat.name])
        default_loss = shrinkage._loss_for(stat, played, stat.default_k)
        if fitted_loss is None or default_loss is None:
            continue
        assert fitted_loss <= default_loss + 1e-12, stat.name
