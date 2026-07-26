"""The fitted v3 model: every component, the choices made about it, and I/O.

Kept apart from ml/train_v3.py so that training and inference assemble the
simulator's inputs through exactly one code path — `build_bundle`. A drift
between how a fold was scored and how predictions are written would be invisible
in the metrics and wrong in the app, so there is no second implementation.

Everything that is *chosen* rather than fitted lives in one JSON alongside the
boosters: the count family per component, the negative-binomial dispersions, the
bonus route, the defensive-contribution minutes curve, the shrinkage weights and
the captaincy blend. Nothing about a saved model is implicit.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml import minutes_model, scoring, shrinkage
from ml.components import (
    assists,
    defcon,
    discipline,
    goals,
    saves,
    team_defence,
)
from ml.components import (
    bonus as bonus_component,
)
from ml.components.base import CountModel
from ml.distribution import Bundle, MinutesPool, bonus_expectation
from ml.features import form_eb
from ml.scoring import Scoring

log = logging.getLogger(__name__)

RATE_COMPONENTS = {"goals": goals, "assists": assists, "saves": saves}


@dataclass
class V3Model:
    minutes: lgb.Booster
    rates: dict[str, CountModel]
    team: team_defence.TeamDefenceModel
    bonus: bonus_component.BonusModel
    discipline: discipline.DisciplineModel
    defcon: lgb.Booster | None
    families: dict[str, str] = field(default_factory=dict)
    dc_minutes_scaling: dict[int, float] = field(default_factory=dict)
    shrinkage_ks: dict[str, float] = field(default_factory=dict)
    minutes_pool: MinutesPool | None = None
    upside_lambda: float = 0.0
    #: Boosting rounds each component's early stopping settled on.
    #
    # Carried explicitly rather than read back off the boosters: a refitted
    # booster has no `best_iteration`, so refitting from an already-refitted
    # model silently collapsed every component to ten rounds and produced flat,
    # position-blind rates. Keeping the counts on the model makes the chain
    # fit -> refit(fold) -> refit(all seasons) safe to repeat.
    rounds: dict[str, int] = field(default_factory=dict)

    # ---------------------------------------------------------------- fitting

    @classmethod
    def fit(
        cls,
        fit_frame: pd.DataFrame,
        valid_frame: pd.DataFrame,
        team_fit: pd.DataFrame,
        team_valid: pd.DataFrame,
        features: dict[str, list[str]] | None = None,
    ) -> "V3Model":
        """Train every component on `fit_frame`, early-stopping on `valid_frame`.

        `features` optionally overrides the feature list per component, which is
        what the ablation varies.
        """
        features = features or {}
        model = cls(
            minutes=minutes_model.train(fit_frame, valid_frame),
            rates={
                name: module.train(
                    fit_frame, valid_frame, features.get(name, module.FEATURES)
                )
                for name, module in RATE_COMPONENTS.items()
            },
            team=team_defence.train(team_fit, team_valid),
            bonus=bonus_component.train(
                fit_frame, valid_frame, features.get("bonus", bonus_component.FEATURES)
            ),
            discipline=discipline.train(
                fit_frame,
                valid_frame,
                features.get("discipline", discipline.FEATURES),
            ),
            defcon=defcon.train(
                fit_frame, valid_frame, features.get("defcon", defcon.FEATURES)
            ),
        )
        model.dc_minutes_scaling = defcon.fit_minutes_scaling(fit_frame)
        model.minutes_pool = MinutesPool.from_frame(fit_frame)
        model.families = {name: "poisson" for name in RATE_COMPONENTS}
        model.families["team"] = "poisson"
        model.rounds = {
            "minutes": int(model.minutes.best_iteration or 500),
            **{name: int(m.best_iteration) for name, m in model.rates.items()},
            "team_conceded": int(model.team.best_iteration_conceded),
            "team_scored": int(model.team.best_iteration_scored),
            "bonus_bps": int(model.bonus.best_iteration_bps),
            "bonus_direct": int(model.bonus.best_iteration_direct),
            "discipline": int(model.discipline.best_iteration),
            "defcon": int(model.defcon.best_iteration) if model.defcon else 0,
        }
        return model

    def choose_families(self, valid_frame: pd.DataFrame, team_valid: pd.DataFrame) -> dict:
        """Poisson or negative binomial, per component, on held-out likelihood.

        The mean is identical either way — this only decides how heavy the tail
        of each component is, which is what P(haul) depends on.
        """
        report: dict[str, dict[str, float]] = {}
        for name, module in RATE_COMPONENTS.items():
            model = self.rates[name]
            scores = {
                family: module_holdout(model, valid_frame, module.LABEL, family)
                for family in ("poisson", "nb")
            }
            best = max(scores, key=lambda f: scores[f])
            self.families[name] = best
            model.family = best
            report[name] = {**scores, "chosen": best}
        scores = {
            family: team_defence.holdout_loglik(self.team, team_valid, family)
            for family in ("poisson", "nb")
        }
        best = max(scores, key=lambda f: scores[f])
        self.families["team"] = best
        self.team.family = best
        report["team"] = {**scores, "chosen": best}
        return report

    def choose_bonus_source(
        self, fit_frame: pd.DataFrame, valid_frame: pd.DataFrame
    ) -> dict:
        """Rank-within-fixture BPS, or a direct regression on bonus points.

        Each route is refitted on the training rows before being scored on the
        validation season, since switching route changes the bucketing and
        therefore the distribution behind it.
        """
        from ml.components.base import played

        rows = played(valid_frame)
        actual = rows["bonus"].fillna(0).to_numpy(dtype=float)
        report: dict[str, float | str] = {}
        for source in ("bps", "direct"):
            bonus_component.set_source(self.bonus, source, fit_frame)
            pred = bonus_component.predict(self.bonus, rows)
            report[source] = float(np.abs(actual - pred).mean())
        best = min(("bps", "direct"), key=lambda s: report[s])
        bonus_component.set_source(self.bonus, best, fit_frame)
        report["chosen"] = best
        return report

    # ------------------------------------------------------------- assembling

    def build_bundle(
        self,
        frame: pd.DataFrame,
        team_predictions: pd.DataFrame,
        season_scoring: Scoring,
    ) -> Bundle:
        """Predict every component for `frame` and package it for the simulator.

        `team_predictions` must carry (season_id, fpl_fixture_id, team_code,
        lambda_conceded) — the team model's output for the same fixtures.
        """
        lookup = team_predictions.set_index(
            ["season_id", "fpl_fixture_id", "team_code"]
        )["lambda_conceded"]
        keys = pd.MultiIndex.from_arrays(
            [frame["season_id"], frame["fpl_fixture_id"], frame["team_code"]]
        )
        lam = lookup.reindex(keys).to_numpy(dtype=float)
        # A fixture with no team prediction (rare: a missing Elo history) falls
        # back to the league average rather than dropping the player.
        lam = np.where(np.isnan(lam), np.nanmean(lam) if np.isfinite(np.nanmean(lam)) else 1.4, lam)
        conceded_pmf = self.team.conceded_pmf(lam)

        minutes_probs = minutes_model.predict_proba(self.minutes, frame)
        position = frame["position"].to_numpy(dtype=int)

        rates = {name: model.rate(frame) for name, model in self.rates.items()}
        rates["saves"] = np.where(position == 1, rates["saves"], 0.0)
        cards = discipline.predict(self.discipline, frame)

        return Bundle(
            position=position,
            minutes_probs=minutes_probs,
            goals_rate=rates["goals"],
            assists_rate=rates["assists"],
            saves_rate=rates["saves"],
            conceded_pmf=conceded_pmf,
            p_dc=defcon.predict(self.defcon, frame),
            p_yellow=cards["yellow"],
            p_red=cards["red"],
            bonus_ranks=self.bonus.buckets(frame),
            bonus_model=self.bonus,
            scoring=season_scoring,
            minutes_pool=self.minutes_pool or MinutesPool.from_frame(frame),
            goals_alpha=self.rates["goals"].dispersion_for(position),
            assists_alpha=self.rates["assists"].dispersion_for(position),
            saves_alpha=self.rates["saves"].dispersion_for(position),
            dc_minutes_scaling=self.dc_minutes_scaling,
        )

    def component_evs(
        self, frame: pd.DataFrame, bundle: Bundle
    ) -> pd.DataFrame:
        """Per-component expected points, for the UI's driver panel.

        These are the linear terms of the same arithmetic `simulate` performs, so
        they explain the total in the model's own units: "4.1 points of which 2.6
        is the goal threat" rather than a list of feature contributions.
        """
        sc = bundle.scoring
        exposure = bundle.minutes_probs[:, 2] + bundle.minutes_probs[:, 1] * (
            (bundle.minutes_pool.cameo.mean() / 90.0) if bundle.minutes_pool else 0.28
        )

        def lut(mapping: dict[int, int]) -> np.ndarray:
            arr = np.zeros(5)
            for k, v in mapping.items():
                arr[k] = v
            return arr[bundle.position]

        played = bundle.minutes_probs[:, 1] + bundle.minutes_probs[:, 2]
        return pd.DataFrame(
            {
                "appearance": bundle.minutes_probs[:, 2] * sc.long_play
                + bundle.minutes_probs[:, 1] * sc.short_play,
                "goals": lut(sc.goals) * bundle.goals_rate * exposure,
                "assists": sc.assists * bundle.assists_rate * exposure,
                "clean_sheet": lut(sc.clean_sheets)
                * bundle.conceded_pmf[:, 0]
                * bundle.minutes_probs[:, 2],
                "saves": sc.saves
                * bundle.saves_rate
                * exposure
                / scoring.SAVES_PER_POINT,
                "defensive": lut(sc.defensive_contribution)
                * bundle.p_dc
                * bundle.minutes_probs[:, 2],
                "bonus": sc.bonus * bonus_expectation(bundle, exposure) * played,
                "cards": sc.yellow_cards * bundle.p_yellow * played
                + sc.red_cards * bundle.p_red * played,
            },
            index=frame.index,
        )

    # -------------------------------------------------------------------- I/O

    def save(self, directory: Path, version: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.minutes.save_model(str(directory / f"model_minutes_{version}.txt"))
        for name, model in self.rates.items():
            model.booster.save_model(str(directory / f"model_{name}_{version}.txt"))
        self.team.conceded.save_model(
            str(directory / f"model_team_conceded_{version}.txt")
        )
        self.team.scored.save_model(str(directory / f"model_team_scored_{version}.txt"))
        self.bonus.bps_model.save_model(str(directory / f"model_bps_{version}.txt"))
        self.bonus.direct_model.save_model(
            str(directory / f"model_bonus_direct_{version}.txt")
        )
        self.discipline.yellow.save_model(str(directory / f"model_yellow_{version}.txt"))
        if self.defcon is not None:
            self.defcon.save_model(str(directory / f"model_defcon_{version}.txt"))

        (directory / f"meta_{version}.json").write_text(
            json.dumps(
                {
                    "families": self.families,
                    "alpha": {
                        name: {str(k): v for k, v in model.alpha.items()}
                        for name, model in self.rates.items()
                    },
                    "team_alpha_conceded": self.team.alpha_conceded,
                    "bonus_source": self.bonus.source,
                    "bonus_direct_edges": self.bonus.direct_edges,
                    "bonus_distribution": bonus_component.distribution_to_json(
                        self.bonus
                    ),
                    "red_rate": {str(k): v for k, v in self.discipline.red_rate.items()},
                    "dc_minutes_scaling": {
                        str(k): v for k, v in self.dc_minutes_scaling.items()
                    },
                    "shrinkage": self.shrinkage_ks,
                    "minutes_pool": {
                        "cameo": _histogram(self.minutes_pool.cameo),
                        "start": _histogram(self.minutes_pool.start),
                    },
                    "upside_lambda": self.upside_lambda,
                    "rounds": self.rounds,
                    "has_defcon": self.defcon is not None,
                },
                indent=2,
            )
        )
        log.info("saved v3 artifacts to %s", directory)

    @classmethod
    def load(cls, directory: Path, version: str) -> "V3Model":
        meta = json.loads((directory / f"meta_{version}.json").read_text())

        def booster(name: str) -> lgb.Booster:
            return lgb.Booster(model_file=str(directory / f"model_{name}_{version}.txt"))

        rates = {}
        for name, module in RATE_COMPONENTS.items():
            rates[name] = CountModel(
                booster=booster(name),
                features=module.FEATURES,
                best_iteration=0,
                alpha={int(k): v for k, v in meta["alpha"].get(name, {}).items()},
                family=meta["families"].get(name, "poisson"),
            )
        team = team_defence.TeamDefenceModel(
            conceded=booster("team_conceded"),
            scored=booster("team_scored"),
            best_iteration_conceded=0,
            best_iteration_scored=0,
            alpha_conceded=meta.get("team_alpha_conceded", 0.0),
            family=meta["families"].get("team", "poisson"),
        )
        bonus = bonus_component.BonusModel(
            bps_model=booster("bps"),
            direct_model=booster("bonus_direct"),
            best_iteration_bps=0,
            best_iteration_direct=0,
            source=meta.get("bonus_source", "bps"),
            rank_distribution=bonus_component.distribution_from_json(
                meta["bonus_distribution"]
            ),
            direct_edges=list(meta.get("bonus_direct_edges", [])),
        )
        disc = discipline.DisciplineModel(
            yellow=booster("yellow"),
            best_iteration=0,
            red_rate={int(k): v for k, v in meta["red_rate"].items()},
        )
        return cls(
            minutes=booster("minutes"),
            rates=rates,
            team=team,
            bonus=bonus,
            discipline=disc,
            defcon=booster("defcon") if meta.get("has_defcon") else None,
            families=meta["families"],
            dc_minutes_scaling={
                int(k): v for k, v in meta["dc_minutes_scaling"].items()
            },
            shrinkage_ks={k: float(v) for k, v in meta.get("shrinkage", {}).items()},
            minutes_pool=MinutesPool(
                cameo=_from_histogram(meta["minutes_pool"]["cameo"]),
                start=_from_histogram(meta["minutes_pool"]["start"]),
            ),
            upside_lambda=float(meta.get("upside_lambda", 0.0)),
            rounds={k: int(v) for k, v in meta.get("rounds", {}).items()},
        )


def module_holdout(
    model: CountModel, frame: pd.DataFrame, label: str, family: str
) -> float:
    from ml.components.base import holdout_loglik

    return holdout_loglik(model, frame, label, family)


def _histogram(values: np.ndarray) -> dict[str, int]:
    """Minutes are integers in 0..120, so the pool round-trips as counts."""
    unique, counts = np.unique(np.asarray(values, dtype=int), return_counts=True)
    return {str(int(u)): int(c) for u, c in zip(unique, counts)}


def _from_histogram(hist: dict[str, int]) -> np.ndarray:
    return np.repeat(
        np.array([int(k) for k in hist], dtype=float),
        np.array([int(v) for v in hist.values()]),
    )


def refit_full(
    frame: pd.DataFrame,
    team_frame: pd.DataFrame,
    fold_model: "V3Model",
    features: dict[str, list[str]] | None = None,
) -> "V3Model":
    """Refit every component on all available seasons, reusing the fold's chosen
    iteration counts, families and selections."""
    features = features or {}
    rounds = fold_model.rounds
    rates = {}
    for name, module in RATE_COMPONENTS.items():
        source = fold_model.rates[name]
        rates[name] = module.refit(
            frame,
            rounds.get(name, 200),
            features.get(name),
            alpha=source.alpha,
            family=source.family,
        )
    model = V3Model(
        minutes=minutes_model.refit(frame, rounds.get("minutes", 500)),
        rates=rates,
        team=team_defence.refit(
            team_frame,
            rounds.get("team_conceded", 200),
            rounds.get("team_scored", 200),
            alpha_conceded=fold_model.team.alpha_conceded,
            family=fold_model.team.family,
        ),
        bonus=bonus_component.refit(
            frame,
            rounds.get("bonus_bps", 200),
            rounds.get("bonus_direct", 200),
            features.get("bonus"),
            source=fold_model.bonus.source,
        ),
        discipline=discipline.refit(
            frame, rounds.get("discipline", 200), features.get("discipline")
        ),
        defcon=defcon.refit(
            frame, rounds.get("defcon") or 200, features.get("defcon")
        ),
        families=dict(fold_model.families),
        dc_minutes_scaling=defcon.fit_minutes_scaling(frame),
        shrinkage_ks=dict(fold_model.shrinkage_ks),
        minutes_pool=MinutesPool.from_frame(frame),
        upside_lambda=fold_model.upside_lambda,
        rounds=dict(rounds),
    )
    return model


def fit_shrinkage(frame: pd.DataFrame) -> dict[str, float]:
    """Fit the empirical-Bayes weights on these rows and rebuild the blended
    columns in place. Callers pass training-fold rows only."""
    return shrinkage.fit_ks(frame)


def apply_shrinkage(frame: pd.DataFrame, ks: dict[str, float]) -> pd.DataFrame:
    return form_eb.apply(frame, ks)
