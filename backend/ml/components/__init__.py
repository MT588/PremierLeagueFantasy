"""Per-component models behind v3's expected points.

v2 asked one regressor to learn `total_points`. But FPL points are a known
linear function of countable events, so v3 models the events and does the
arithmetic exactly (ml/scoring.py):

    goals, assists      count models, per 90, Poisson or negative binomial
    clean sheet / GC    a team-level goals-conceded model shared by the XI
    saves               count model driven by the shots a keeper faces
    defensive actions   probability of clearing the positional DC threshold
    bonus               BPS ranked within the fixture, mapped to bonus points
    cards               a small negative term with suspension context

Each module exposes the same four calls — `FEATURES`, `train`, `refit`,
`predict` — so ml/train_v3.py, the ablation and the Monte-Carlo simulator treat
them interchangeably.
"""

from ml.components import (
    assists,
    bonus,
    defcon,
    discipline,
    goals,
    saves,
    team_defence,
)

#: Player-level components, in the order the training report lists them.
PLAYER_COMPONENTS = (goals, assists, saves, defcon, bonus, discipline)

__all__ = [
    "PLAYER_COMPONENTS",
    "assists",
    "bonus",
    "defcon",
    "discipline",
    "goals",
    "saves",
    "team_defence",
]
