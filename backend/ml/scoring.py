"""The official FPL scoring matrix — the one place points arithmetic lives.

v3 predicts countable events (goals, assists, clean sheets, saves, defensive
contributions, cards, bonus) and turns them into points here. That makes the
combination step exact rather than fitted: `reconstruct_points` reproduces the
recorded `total_points` for every historical row, which is a test gate
(tests/test_scoring_v3.py).

Two rule details are NOT published in the API payload and so live here as
curated constants: goals conceded score every *second* goal, saves every
*third* save, and the defensive-contribution threshold is positional (10 for
defenders, 12 for midfielders and forwards). `derive_dc_thresholds` recovers
the thresholds from data, so a mid-season change shows up as a failing test
instead of quietly mispricing every defender.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

POSITION_KEYS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

GOALS_CONCEDED_PER_POINT = 2
SAVES_PER_POINT = 3

# Positional defensive-contribution thresholds (2025-26 rule). Defenders count
# tackles + clearances/blocks/interceptions; midfielders and forwards also count
# recoveries; keepers do not score the bonus at all.
DC_THRESHOLDS: dict[int, int] = {1: 0, 2: 10, 3: 12, 4: 12}


@dataclass(frozen=True)
class Scoring:
    """Points per event for one season. Position-dependent values are indexed by
    the FPL position id (1 GK, 2 DEF, 3 MID, 4 FWD)."""

    season: str
    long_play: int
    short_play: int
    goals: dict[int, int]
    assists: int
    clean_sheets: dict[int, int]
    goals_conceded: dict[int, int]
    saves: int
    penalties_saved: int
    penalties_missed: int
    yellow_cards: int
    red_cards: int
    own_goals: int
    bonus: int
    defensive_contribution: dict[int, int]
    dc_thresholds: dict[int, int]

    @property
    def has_defensive_contribution(self) -> bool:
        return any(v for v in self.defensive_contribution.values())


def _by_position(d: Mapping[str, int]) -> dict[int, int]:
    return {pos: int(d[key]) for pos, key in POSITION_KEYS.items() if key in d}


def _lut(d: Mapping[int, int]) -> np.ndarray:
    """Position-indexed lookup array so scoring broadcasts over any array shape
    (rows, or rows x Monte-Carlo draws)."""
    out = np.zeros(5, dtype=float)
    for pos, value in d.items():
        out[pos] = value
    return out


# Rules for the seasons in the archive. Identical throughout except that the
# defensive-contribution bonus arrived in 2025-26; 2026-27 raised a keeper's
# goal from 6 to 10 and is read from the live API payload instead.
_PRE_DC = {
    "long_play": 2,
    "short_play": 1,
    "goals": {1: 6, 2: 6, 3: 5, 4: 4},
    "assists": 3,
    "clean_sheets": {1: 4, 2: 4, 3: 1, 4: 0},
    "goals_conceded": {1: -1, 2: -1, 3: 0, 4: 0},
    "saves": 1,
    "penalties_saved": 5,
    "penalties_missed": -2,
    "yellow_cards": -1,
    "red_cards": -3,
    "own_goals": -2,
    "bonus": 1,
    "defensive_contribution": {1: 0, 2: 0, 3: 0, 4: 0},
    "dc_thresholds": DC_THRESHOLDS,
}
_WITH_DC = {**_PRE_DC, "defensive_contribution": {1: 0, 2: 2, 3: 2, 4: 2}}

CURATED: dict[str, dict] = {
    "2021-22": _PRE_DC,
    "2022-23": _PRE_DC,
    "2023-24": _PRE_DC,
    "2024-25": _PRE_DC,
    "2025-26": _WITH_DC,
}


def from_api_config(season: str, config: dict) -> Scoring:
    """Build a Scoring from bootstrap-static.game_config."""
    s = config["scoring"]
    return Scoring(
        season=season,
        long_play=int(s["long_play"]),
        short_play=int(s["short_play"]),
        goals=_by_position(s["goals_scored"]),
        assists=int(s["assists"]),
        clean_sheets=_by_position(s["clean_sheets"]),
        goals_conceded=_by_position(s["goals_conceded"]),
        saves=int(s["saves"]),
        penalties_saved=int(s["penalties_saved"]),
        penalties_missed=int(s["penalties_missed"]),
        yellow_cards=int(s["yellow_cards"]),
        red_cards=int(s["red_cards"]),
        own_goals=int(s["own_goals"]),
        bonus=int(s["bonus"]),
        defensive_contribution=_by_position(s["defensive_contribution"]),
        dc_thresholds=DC_THRESHOLDS,
    )


def for_season(season: str) -> Scoring:
    """Curated rules for archived seasons, the live (cached) API payload for
    anything newer. Offline-safe for every season in the archive."""
    if season in CURATED:
        return Scoring(season=season, **CURATED[season])
    from pipeline import fpl_api

    return from_api_config(season, fpl_api.game_config(season))


COMPONENTS = (
    "minutes",
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "saves",
    "penalties_saved",
    "penalties_missed",
    "yellow_cards",
    "red_cards",
    "own_goals",
    "bonus",
    "defensive_contribution",
)


def points_from_components(
    components: Mapping[str, np.ndarray],
    position: np.ndarray,
    scoring: Scoring,
) -> np.ndarray:
    """Points from event counts. Every argument broadcasts, so this serves both
    one row per player-fixture and a (rows x draws) Monte-Carlo block — pass
    `position` as a column vector in the latter case.

    Missing components default to zero, which lets callers score a partial set
    (e.g. an outfield player has no saves).
    """

    def c(name: str) -> np.ndarray:
        value = components.get(name)
        return np.zeros(1) if value is None else np.asarray(value, dtype=float)

    pos = np.asarray(position, dtype=int)
    minutes = c("minutes")

    pts = np.where(minutes >= 60, scoring.long_play, np.where(minutes > 0, scoring.short_play, 0.0))
    pts = pts + _lut(scoring.goals)[pos] * c("goals_scored")
    pts = pts + scoring.assists * c("assists")
    pts = pts + _lut(scoring.clean_sheets)[pos] * c("clean_sheets")
    # Every second goal conceded costs a point, and only for keepers/defenders.
    pts = pts + _lut(scoring.goals_conceded)[pos] * (
        c("goals_conceded") // GOALS_CONCEDED_PER_POINT
    )
    pts = pts + scoring.saves * (c("saves") // SAVES_PER_POINT)
    pts = pts + scoring.penalties_saved * c("penalties_saved")
    pts = pts + scoring.penalties_missed * c("penalties_missed")
    pts = pts + scoring.yellow_cards * c("yellow_cards")
    pts = pts + scoring.red_cards * c("red_cards")
    pts = pts + scoring.own_goals * c("own_goals")
    pts = pts + scoring.bonus * c("bonus")
    if scoring.has_defensive_contribution:
        hit = c("defensive_contribution") >= _lut(scoring.dc_thresholds)[pos]
        pts = pts + _lut(scoring.defensive_contribution)[pos] * hit
    return pts


def reconstruct_points(frame: pd.DataFrame, scoring: Scoring | None = None) -> np.ndarray:
    """Score a player_gameweeks-shaped frame with its own season's rules."""
    scoring = scoring or for_season(str(frame["season_name"].iloc[0]))
    components = {
        name: frame[name].fillna(0).to_numpy(dtype=float)
        for name in COMPONENTS
        if name in frame.columns
    }
    return points_from_components(
        components, frame["position"].to_numpy(dtype=int), scoring
    )


def derive_dc_thresholds(frame: pd.DataFrame, scoring: Scoring) -> dict[int, int]:
    """Recover the positional defensive-contribution thresholds from scored
    history: the residual left after scoring every other component is either 0
    or the DC award, which brackets the threshold from both sides.

    Returns a position -> threshold map for the positions the season awards DC
    for; a position whose residuals never fire is omitted.
    """
    no_dc = points_from_components(
        {
            name: frame[name].fillna(0).to_numpy(dtype=float)
            for name in COMPONENTS
            if name in frame.columns and name != "defensive_contribution"
        },
        frame["position"].to_numpy(dtype=int),
        scoring,
    )
    residual = frame["total_points"].to_numpy(dtype=float) - no_dc
    dc = frame["defensive_contribution"].fillna(0).to_numpy(dtype=float)
    positions = frame["position"].to_numpy(dtype=int)

    out: dict[int, int] = {}
    for pos, award in scoring.defensive_contribution.items():
        if not award:
            continue
        mask = positions == pos
        fired = mask & np.isclose(residual, award)
        quiet = mask & np.isclose(residual, 0)
        if not fired.any():
            continue
        low = int(dc[fired].min())
        high = int(dc[quiet].max()) if quiet.any() else low - 1
        if high >= low:
            raise ValueError(
                f"position {pos}: DC counts overlap across the threshold "
                f"(awarded from {low}, withheld up to {high}) — scoring rules changed"
            )
        out[pos] = low
    return out
