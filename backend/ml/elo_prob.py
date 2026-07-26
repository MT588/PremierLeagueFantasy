"""Elo -> three-way match probabilities, calibrated against bookmaker odds.

Betting odds only exist for played matches, so they can't be inference
features. Instead we fit a small parametric map from Elo difference to
(home/draw/away) probabilities against the odds-implied probabilities of
2021-2025, freeze the parameters, and use Elo-implied probabilities as the
model feature — identical for training rows and future fixtures.

Model: d = home_elo + hfa - away_elo
       E_home  = 1 / (1 + 10^(-d/400))          (classic Elo expectation)
       p_draw  = c * exp(-d^2 / (2 s^2))         (draws peak at equal strength)
       p_home  = E_home - p_draw/2, p_away = 1 - p_home - p_draw (clipped+renormed)
Parameters (hfa, c, s) minimize cross-entropy vs odds-implied probs.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sqlalchemy import text

log = logging.getLogger(__name__)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
PARAMS_FILE = ARTIFACTS / "elo_prob_params.json"
EPS = 1e-6

FIT_SQL = """
select f.season_id, s.name as season_name, f.fpl_fixture_id,
       f.home_score, f.away_score,
       eh.elo as home_elo, ea.elo as away_elo,
       o.b365_home, o.b365_draw, o.b365_away
from fixtures f
join seasons s on s.id = f.season_id
join match_odds o using (season_id, fpl_fixture_id)
join lateral (
  select elo from club_elo e where e.team_code = f.home_team_code
    and e.valid_from <= f.kickoff_time::date - 1
  order by e.valid_from desc limit 1) eh on true
join lateral (
  select elo from club_elo e where e.team_code = f.away_team_code
    and e.valid_from <= f.kickoff_time::date - 1
  order by e.valid_from desc limit 1) ea on true
where f.finished and o.b365_home is not null
"""


def elo_probs(d: np.ndarray, hfa: float, c: float, s: float) -> np.ndarray:
    """Return (n,3) array of [p_home, p_draw, p_away] for elo diffs d (home-away)."""
    dd = d + hfa
    e_home = 1.0 / (1.0 + 10 ** (-dd / 400.0))
    p_draw = np.clip(c * np.exp(-(dd**2) / (2 * s**2)), EPS, 0.6)
    p_home = np.clip(e_home - p_draw / 2, EPS, None)
    p_away = np.clip(1.0 - p_home - p_draw, EPS, None)
    p = np.stack([p_home, p_draw, p_away], axis=1)
    return p / p.sum(axis=1, keepdims=True)


def implied_probs(df: pd.DataFrame) -> np.ndarray:
    inv = np.stack(
        [1 / df["b365_home"], 1 / df["b365_draw"], 1 / df["b365_away"]], axis=1
    )
    return inv / inv.sum(axis=1, keepdims=True)


def outcomes(df: pd.DataFrame) -> np.ndarray:
    """0=home win, 1=draw, 2=away win."""
    return np.select(
        [df["home_score"] > df["away_score"], df["home_score"] == df["away_score"]],
        [0, 1],
        default=2,
    )


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(p[np.arange(len(y)), y] + EPS).mean())


def fit(engine, holdout_season: str = "2025-26") -> dict:
    with engine.connect() as conn:
        df = pd.read_sql(text(FIT_SQL), conn)
    train = df[df["season_name"] != holdout_season]
    test = df[df["season_name"] == holdout_season]

    d_train = (train["home_elo"] - train["away_elo"]).to_numpy(dtype=float)
    target = implied_probs(train)

    def objective(theta):
        p = elo_probs(d_train, *theta)
        return -(target * np.log(p + EPS)).sum(axis=1).mean()

    res = minimize(objective, x0=[50.0, 0.30, 300.0], method="Nelder-Mead")
    hfa, c, s = res.x
    params = {"hfa": float(hfa), "c": float(c), "s": float(s)}

    d_test = (test["home_elo"] - test["away_elo"]).to_numpy(dtype=float)
    y = outcomes(test)
    report = {
        **params,
        "holdout_season": holdout_season,
        "n_train": len(train),
        "n_test": len(test),
        "logloss_elo": log_loss(elo_probs(d_test, hfa, c, s), y),
        "logloss_odds": log_loss(implied_probs(test), y),
    }
    ARTIFACTS.mkdir(exist_ok=True)
    PARAMS_FILE.write_text(json.dumps(report, indent=2))
    log.info("elo_prob fit: %s", report)
    return report


def load_params() -> dict:
    return json.loads(PARAMS_FILE.read_text())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from app.db import engine

    print(json.dumps(fit(engine), indent=2))
