"""Team-level goals conceded and scored — the clean-sheet component.

A clean sheet is not a player property. Eleven players share one outcome, so it
is modelled once per team-fixture and then priced per position by the scoring
matrix (4 points for a keeper or defender, 1 for a midfielder, 0 for a forward,
and a point off every second goal conceded for keepers and defenders).

Working at team level also buys the exact label — `fixtures.home_score` /
`away_score` rather than a per-player `goals_conceded` that depends on when the
player came off — and a much smaller frame: ~3,800 team-fixtures against 139k
player-gameweeks.

The same frame yields the goals-scored rate, which ml/components/saves.py uses
as the shots proxy a keeper faces and which the report uses to sanity-check that
per-player goal rates sum to something like the team total.
"""

import logging
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from ml import elo_prob
from ml.components.base import ALPHA_GRID, NUM_BOOST_ROUND, PARAMS, _nb_loglik
from ml.features.context import FeatureContext

log = logging.getLogger(__name__)

FEATURES = [
    "was_home_i",
    "own_elo",
    "opp_elo",
    "elo_diff",
    "p_win_elo",
    "p_draw_elo",
    "p_loss_elo",
    "own_ga_6",
    "own_gf_6",
    "own_cs_10",
    "opp_ga_6",
    "opp_gf_6",
    "opp_cs_10",
    "own_xgc_6",
    "opp_xgc_6",
    "days_rest",
    "gw_number",
]

TEAM_SQL = """
select f.season_id, s.start_year, s.name as season_name, f.fpl_fixture_id,
       f.gameweek, f.kickoff_time, f.home_team_code, f.away_team_code,
       f.home_score, f.away_score, f.finished,
       ts_h.strength_defence_home, ts_h.strength_attack_home,
       ts_a.strength_defence_away, ts_a.strength_attack_away
from fixtures f
join seasons s on s.id = f.season_id
left join team_seasons ts_h on ts_h.season_id = f.season_id and ts_h.team_code = f.home_team_code
left join team_seasons ts_a on ts_a.season_id = f.season_id and ts_a.team_code = f.away_team_code
where f.kickoff_time is not null
"""

ROLL_WINDOW = 6
CS_WINDOW = 10


def _team_xgc(engine: Engine) -> pd.DataFrame:
    """Expected goals conceded per team-fixture, taken as the largest value
    recorded by any player who was on the pitch for an hour — for a keeper who
    played the full match that is exactly the team's xGC."""
    sql = """
    select g.season_id, g.fpl_fixture_id, ps.team_code,
           max(g.expected_goals_conceded) as xgc
    from player_gameweeks g
    join player_seasons ps
      on ps.season_id = g.season_id and ps.player_code = g.player_code
    where g.minutes >= 60 and g.expected_goals_conceded is not null
    group by g.season_id, g.fpl_fixture_id, ps.team_code
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def build_team_frame(engine: Engine, ctx: FeatureContext) -> pd.DataFrame:
    """One row per team per fixture, with leakage-safe rolling form for both
    sides. Unfinished fixtures are kept so inference uses the same builder."""
    with engine.connect() as conn:
        fixtures = pd.read_sql(text(TEAM_SQL), conn)
    fixtures["kickoff_time"] = pd.to_datetime(
        fixtures["kickoff_time"], utc=True
    ).astype("datetime64[ns, UTC]")

    home = fixtures.rename(
        columns={
            "home_team_code": "team_code",
            "away_team_code": "opponent_team_code",
            "home_score": "goals_for",
            "away_score": "goals_against",
        }
    ).assign(was_home_i=1.0)
    away = fixtures.rename(
        columns={
            "away_team_code": "team_code",
            "home_team_code": "opponent_team_code",
            "away_score": "goals_for",
            "home_score": "goals_against",
        }
    ).assign(was_home_i=0.0)
    keep = [
        "season_id",
        "start_year",
        "season_name",
        "fpl_fixture_id",
        "gameweek",
        "kickoff_time",
        "team_code",
        "opponent_team_code",
        "goals_for",
        "goals_against",
        "finished",
        "was_home_i",
    ]
    df = pd.concat([home[keep], away[keep]], ignore_index=True)
    df = df.sort_values(["team_code", "kickoff_time"]).reset_index(drop=True)

    xgc = _team_xgc(engine)
    df = df.merge(xgc, on=["season_id", "fpl_fixture_id", "team_code"], how="left")

    # rolling own form, all lagged one match
    g = df.groupby("team_code", sort=False)
    df["own_ga_6"] = g["goals_against"].transform(
        lambda s: s.shift(1).rolling(ROLL_WINDOW, min_periods=2).mean()
    )
    df["own_gf_6"] = g["goals_for"].transform(
        lambda s: s.shift(1).rolling(ROLL_WINDOW, min_periods=2).mean()
    )
    # `.eq(0)` maps a null to False, which would score an unplayed fixture as
    # "conceded" — mask first so an unknown result stays unknown.
    df["own_cs_10"] = g["goals_against"].transform(
        lambda s: s.shift(1)
        .eq(0)
        .where(s.shift(1).notna())
        .rolling(CS_WINDOW, min_periods=3)
        .mean()
    )
    df["own_xgc_6"] = g["xgc"].transform(
        lambda s: s.shift(1).rolling(ROLL_WINDOW, min_periods=2).mean()
    )
    df["days_rest"] = (
        g["kickoff_time"].transform(lambda s: s - s.shift(1)).dt.days.clip(0, 60)
    )
    df["gw_number"] = df["gameweek"]

    # the opponent's own form, joined onto this row as-of this kickoff
    opp = df[
        ["team_code", "kickoff_time", "own_ga_6", "own_gf_6", "own_cs_10", "own_xgc_6"]
    ].rename(
        columns={
            "team_code": "opponent_team_code",
            "own_ga_6": "opp_ga_6",
            "own_gf_6": "opp_gf_6",
            "own_cs_10": "opp_cs_10",
            "own_xgc_6": "opp_xgc_6",
        }
    )
    df = df.merge(
        opp, on=["opponent_team_code", "kickoff_time"], how="left", validate="1:1"
    )

    df = _add_elo(df, ctx)
    return df


def _add_elo(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    """As-of Elo for both sides plus the calibrated outcome probabilities. The
    same lookup the player-level opponent/market groups use."""
    elo = ctx.club_elo.sort_values("valid_from")
    for team_col, out in (("team_code", "own_elo"), ("opponent_team_code", "opp_elo")):
        left = (
            df[[team_col, "kickoff_time"]]
            .reset_index()
            .dropna(subset=["kickoff_time", team_col])
            .sort_values("kickoff_time")
        )
        right = elo.rename(
            columns={"team_code": team_col, "valid_from": "kickoff_time"}
        )
        merged = pd.merge_asof(
            left, right, on="kickoff_time", by=team_col, direction="backward"
        ).set_index("index")
        df[out] = merged["elo"].reindex(df.index)
    df["elo_diff"] = df["own_elo"] - df["opp_elo"]

    params = elo_prob.load_params()
    home_diff = np.where(
        df["was_home_i"] > 0,
        df["own_elo"] - df["opp_elo"],
        df["opp_elo"] - df["own_elo"],
    ).astype(float)
    valid = ~np.isnan(home_diff)
    probs = np.full((len(df), 3), np.nan)
    if valid.any():
        probs[valid] = elo_prob.elo_probs(
            home_diff[valid], params["hfa"], params["c"], params["s"]
        )
    is_home = (df["was_home_i"] > 0).to_numpy()
    df["p_win_elo"] = np.where(is_home, probs[:, 0], probs[:, 2])
    df["p_draw_elo"] = probs[:, 1]
    df["p_loss_elo"] = np.where(is_home, probs[:, 2], probs[:, 0])
    return df


def _train_one(
    fit: pd.DataFrame, valid: pd.DataFrame, label: str
) -> tuple[lgb.Booster, int]:
    dtrain = lgb.Dataset(fit[FEATURES], label=fit[label].to_numpy(dtype=float))
    dvalid = lgb.Dataset(
        valid[FEATURES], label=valid[label].to_numpy(dtype=float), reference=dtrain
    )
    booster = lgb.train(
        PARAMS,
        dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    return booster, booster.best_iteration or NUM_BOOST_ROUND


@dataclass
class TeamDefenceModel:
    """Goals-conceded and goals-scored rates per team-fixture, plus the count
    law used to turn the conceded rate into clean-sheet and goals-conceded
    points."""

    conceded: lgb.Booster
    scored: lgb.Booster
    best_iteration_conceded: int
    best_iteration_scored: int
    alpha_conceded: float = 0.0
    family: str = "poisson"

    def predict(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        return {
            "conceded": np.clip(
                self.conceded.predict(
                    df[FEATURES], num_iteration=self.best_iteration_conceded or None
                ),
                0.01,
                None,
            ),
            "scored": np.clip(
                self.scored.predict(
                    df[FEATURES], num_iteration=self.best_iteration_scored or None
                ),
                0.01,
                None,
            ),
        }

    def conceded_pmf(self, lam: np.ndarray, max_goals: int = 10) -> np.ndarray:
        """P(goals conceded = k) for k in 0..max_goals, one row per fixture.

        Clean-sheet probability is column 0, and the goals-conceded penalty is
        the expectation of floor(k / 2) over the same distribution — both read
        off one array rather than approximated.
        """
        lam = np.asarray(lam, dtype=float).reshape(-1, 1)
        k = np.arange(max_goals + 1).reshape(1, -1)
        if self.family == "nb" and self.alpha_conceded > 0:
            from scipy.stats import nbinom

            r = 1.0 / self.alpha_conceded
            p = r / (r + lam)
            pmf = nbinom.pmf(k, r, p)
        else:
            from scipy.stats import poisson

            pmf = poisson.pmf(k, lam)
        total = pmf.sum(axis=1, keepdims=True)
        return pmf / np.where(total > 0, total, 1.0)


def train(fit: pd.DataFrame, valid: pd.DataFrame) -> TeamDefenceModel:
    fit, valid = finished(fit), finished(valid)
    conceded, it_c = _train_one(fit, valid, "goals_against")
    scored, it_s = _train_one(fit, valid, "goals_for")
    model = TeamDefenceModel(
        conceded=conceded,
        scored=scored,
        best_iteration_conceded=it_c,
        best_iteration_scored=it_s,
    )
    model.alpha_conceded = _fit_alpha(model, fit)
    return model


def refit(
    full: pd.DataFrame,
    best_iteration_conceded: int,
    best_iteration_scored: int,
    alpha_conceded: float = 0.0,
    family: str = "poisson",
) -> TeamDefenceModel:
    full = finished(full)
    out = {}
    for label, rounds in (
        ("goals_against", best_iteration_conceded),
        ("goals_for", best_iteration_scored),
    ):
        dtrain = lgb.Dataset(full[FEATURES], label=full[label].to_numpy(dtype=float))
        out[label] = lgb.train(PARAMS, dtrain, num_boost_round=max(rounds, 10))
    return TeamDefenceModel(
        conceded=out["goals_against"],
        scored=out["goals_for"],
        best_iteration_conceded=0,
        best_iteration_scored=0,
        alpha_conceded=alpha_conceded,
        family=family,
    )


def finished(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["finished"] & df["goals_against"].notna()]


def _fit_alpha(model: TeamDefenceModel, frame: pd.DataFrame) -> float:
    lam = model.predict(frame)["conceded"]
    y = frame["goals_against"].to_numpy(dtype=float)
    return float(max(ALPHA_GRID, key=lambda a: _nb_loglik(y, lam, a)))


def holdout_loglik(
    model: TeamDefenceModel, frame: pd.DataFrame, family: str
) -> float:
    frame = finished(frame)
    if frame.empty:
        return float("nan")
    lam = model.predict(frame)["conceded"]
    y = frame["goals_against"].to_numpy(dtype=float)
    alpha = model.alpha_conceded if family == "nb" else 0.0
    return _nb_loglik(y, lam, alpha) / len(frame)
