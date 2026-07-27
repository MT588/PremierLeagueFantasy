"""The v3 scoring matrix, checked against every archived row.

v3's combination step is arithmetic, not a fitted model: components are priced
by ml/scoring.py and summed. That is only sound if the same function reproduces
recorded history exactly, so this reconstructs `total_points` for all ~139k
archived player-gameweeks under each season's own rules.

The per-season split matters. 2021-22 to 2024-25 have no defensive-contribution
award; 2025-26 adds it. Scoring a frame with the wrong season's rules is silent
— it just misprices — so a season that regresses has to fail here.
"""

import numpy as np
import pandas as pd
import pytest

from app.db import engine
from ml import scoring
from ml.features.base import load_history


@pytest.fixture(scope="module")
def history() -> pd.DataFrame:
    df = load_history(engine)
    # rows the archive never filled in cannot be reconstructed from components
    return df[df["total_points"].notna()]


def _reconstruct(frame: pd.DataFrame) -> np.ndarray:
    return scoring.reconstruct_points(frame, scoring.for_season(str(frame["season_name"].iloc[0])))


def test_every_season_reconstructs_exactly(history):
    """Not 'close' — equal. A single mispriced event is a bug in the matrix."""
    failures = {}
    for season, frame in history.groupby("season_name"):
        exact = np.isclose(_reconstruct(frame), frame["total_points"].to_numpy(dtype=float))
        if not exact.all():
            failures[season] = {
                "rows": len(frame),
                "mismatched": int((~exact).sum()),
                "example": frame.loc[~exact, ["player_code", "gameweek", "total_points"]]
                .head(3)
                .to_dict("records"),
            }
    assert not failures, failures


def test_the_whole_archive_reconstructs(history):
    """The headline gate: every row, every season, one number."""
    reconstructed = np.concatenate(
        [_reconstruct(frame) for _, frame in history.groupby("season_name")]
    )
    actual = np.concatenate(
        [frame["total_points"].to_numpy(dtype=float) for _, frame in history.groupby("season_name")]
    )
    assert len(actual) > 130_000
    assert np.isclose(reconstructed, actual).all()


def test_current_season_uses_the_defensive_contribution_rule(history):
    """2025-26 is the fold that matters for the live model: it must reconstruct
    under the DC rule and must NOT reconstruct under the pre-DC one, which is
    what proves the award is actually being priced rather than absorbed."""
    frame = history[history["season_name"] == "2025-26"]
    assert len(frame) > 10_000

    with_dc = scoring.for_season("2025-26")
    assert with_dc.has_defensive_contribution
    assert np.isclose(
        scoring.reconstruct_points(frame, with_dc), frame["total_points"].to_numpy(dtype=float)
    ).all()

    without_dc = scoring.for_season("2024-25")
    assert not without_dc.has_defensive_contribution
    mismatched = ~np.isclose(
        scoring.reconstruct_points(frame, without_dc),
        frame["total_points"].to_numpy(dtype=float),
    )
    assert mismatched.any(), "DC award is not being priced — the rule is a no-op"


def test_dc_thresholds_derive_from_data(history):
    """Thresholds are recovered from scored history rather than trusted. A
    mid-season rule change surfaces here instead of quietly mispricing defenders."""
    frame = history[history["season_name"] == "2025-26"]
    derived = scoring.derive_dc_thresholds(frame, scoring.for_season("2025-26"))
    assert derived == {2: 10, 3: 12, 4: 12}
    # and the curated constants agree with what the data says
    curated = scoring.DC_THRESHOLDS
    assert all(curated[pos] == value for pos, value in derived.items())


def test_keeper_goal_is_worth_ten_in_2026_27():
    """The 2026-27 rule change, read from the cached live game_config rather than
    the curated table. Getting this wrong underprices every keeper goal by four."""
    sc = scoring.for_season("2026-27")
    assert sc.goals[1] == 10
    assert sc.goals[4] == 4


def test_step_scoring_is_not_linear():
    """Goals conceded score every second goal and saves every third — the two
    places where using a mean instead of a distribution would be wrong."""
    sc = scoring.for_season("2024-25")
    keeper = np.array([1])

    def points(**components):
        return scoring.points_from_components(
            {"minutes": np.array([90]), **components}, keeper, sc
        )[0]

    # one goal conceded costs nothing; the second costs a point
    assert points(goals_conceded=np.array([1])) == points(goals_conceded=np.array([0]))
    assert points(goals_conceded=np.array([2])) == points(goals_conceded=np.array([0])) - 1
    assert points(goals_conceded=np.array([3])) == points(goals_conceded=np.array([0])) - 1
    # saves pay per third
    assert points(saves=np.array([2])) == points(saves=np.array([0]))
    assert points(saves=np.array([3])) == points(saves=np.array([0])) + 1


def test_appearance_points_switch_at_sixty_minutes():
    sc = scoring.for_season("2024-25")
    mid = np.array([3])

    def points(minutes):
        return scoring.points_from_components(
            {"minutes": np.array([minutes])}, mid, sc
        )[0]

    assert points(0) == 0
    assert points(1) == sc.short_play
    assert points(59) == sc.short_play
    assert points(60) == sc.long_play


def test_scoring_broadcasts_over_a_draw_block():
    """The simulator scores an (n, draws) block with position as a column vector;
    the result must match scoring each row on its own."""
    sc = scoring.for_season("2025-26")
    position = np.array([2, 3, 4]).reshape(-1, 1)
    goals = np.array([[0, 1, 2], [1, 0, 0], [0, 0, 3]], dtype=float)
    minutes = np.full((3, 3), 90.0)

    block = scoring.points_from_components(
        {"minutes": minutes, "goals_scored": goals}, position, sc
    )
    assert block.shape == (3, 3)
    for i in range(3):
        row = scoring.points_from_components(
            {"minutes": minutes[i], "goals_scored": goals[i]},
            np.full(3, position[i, 0]),
            sc,
        )
        assert np.allclose(block[i], row)
