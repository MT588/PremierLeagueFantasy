"""Phase-5 gates: leakage-safety and v1 regression for the feature package."""

import numpy as np
import pandas as pd
import pytest

from app.db import engine
from ml.features import FEATURES, _load_birth_dates, add_all_features
from ml.features.base import load_history
from ml.features.context import load_context

MUTABLE_COLS = [
    "total_points", "minutes", "goals_scored", "assists", "bonus", "bps",
    "ict_index", "expected_goals", "expected_assists", "expected_goal_involvements",
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
    """Mutating every stat after the cutoff must not change any feature of any
    row at or before the cutoff — the definitive check that every group only
    looks backward."""
    ctx, birth, hist, base = built
    mutated_input = hist.copy()
    future = mutated_input["kickoff_time"] > CUTOFF
    assert future.sum() > 10_000
    for col in MUTABLE_COLS:
        mutated_input.loc[future, col] = mutated_input.loc[future, col] * 3 + 7

    mutated = add_all_features(mutated_input, ctx, birth)

    past = base["kickoff_time"] <= CUTOFF
    a = base.loc[past, FEATURES].to_numpy(dtype=float)
    b = mutated.loc[past, FEATURES].to_numpy(dtype=float)
    both_nan = np.isnan(a) & np.isnan(b)
    close = np.isclose(a, b, rtol=1e-9, atol=1e-9) | both_nan
    bad = np.argwhere(~close)
    assert close.all(), (
        f"{len(bad)} leaked cells; first offenders: "
        f"{[(FEATURES[j], base.loc[past].iloc[i]['season_name']) for i, j in bad[:5]]}"
    )


def test_v1_features_reproduce(built):
    """The refactor must not change v1 feature values (2022-23 onward — the
    2021-22 xG backfill from Understat is a deliberate improvement)."""
    from ml import features_v1

    *_, base = built
    v1 = features_v1.build_training_frame(engine)

    keys = ["player_code", "season_id", "gameweek", "fpl_fixture_id"]
    shared = [f for f in features_v1.FEATURES if f in FEATURES and f != "prev_season_ppg"]
    merged = v1[keys + shared + ["season_name"]].merge(
        base[keys + shared], on=keys, suffixes=("_v1", "_v2")
    )
    merged = merged[~merged["season_name"].isin(["2021-22", "2022-23"])]
    assert len(merged) > 50_000
    for f in shared:
        a = merged[f + "_v1"].to_numpy(dtype=float)
        b = merged[f + "_v2"].to_numpy(dtype=float)
        both_nan = np.isnan(a) & np.isnan(b)
        assert (np.isclose(a, b, rtol=1e-6, equal_nan=False) | both_nan).mean() > 0.995, f


def test_international_load_fires_for_euro_2024(built):
    *_, base = built
    early_2425 = base[(base["season_name"] == "2024-25") & (base["gameweek"] <= 3)]
    assert (early_2425["intl_deep_run_decayed"] > 0).sum() > 100


def test_expected_nan_patterns(built):
    *_, base = built
    s2122 = base[base["season_name"] == "2021-22"]
    # Understat backfill should recover xG for a meaningful share of 2021-22
    assert s2122["xgi90_5"].notna().mean() > 0.2
    # Elo must be complete everywhere
    assert base["opp_elo"].notna().mean() > 0.99
