"""Monte-Carlo points distribution: sample minutes, then sample each component.

v2 produced a conditional mean, which cannot answer the question a manager
actually asks — not "how many points will he score" but "what are the odds he
wins me the week". Two players on 6.0 expected points are not interchangeable if
one of them is a 6-every-week defender and the other is a 2-or-15 forward.

Every draw goes through ml/scoring.py, the same function that reproduces
recorded history exactly, so the simulated distribution is on the real points
scale by construction rather than by calibration.

Three details that are easy to get wrong and are handled here:

  - **Expected points come from `analytic_ev`, not from the draws.** A mean of
    integer point totals is granular: over 300 draws it can only take values a
    third of a point apart, which collapsed 29,000 predictions onto 1,700
    distinct values and cost 0.003 of rank correlation to ties alone. `simulate`
    reports the closed form as `ev` and keeps the sampled mean as `ev_mc`, whose
    agreement is the consistency check.

  - **Double gameweeks.** Fixtures are sampled separately and the *draws* are
    summed per player-gameweek before any statistic is taken. Summing quantiles
    instead would overstate both tails.
  - **Team correlation.** Goals conceded is drawn once per fixture and shared by
    that team's players, so a clean sheet is a clean sheet for the whole back
    line rather than eleven independent coin flips.
"""

import itertools
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ml import scoring
from ml.components import base as component_base
from ml.components import bonus as bonus_component
from ml.scoring import Scoring

log = logging.getLogger(__name__)

DEFAULT_DRAWS = 2000
DEFAULT_SEED = 0
# Rows per chunk. Draws dominate memory (rows x draws x components), so the
# frame is walked in blocks and only summary statistics are kept.
CHUNK_ROWS = 4000

HAUL = 10
RETURN = 5
BLANK = 2


@dataclass
class MinutesPool:
    """Observed minutes to resample, split by the class that generated them.

    Sampling real minutes rather than assuming 90 and 23 matters for every rate
    in the simulation, and for the appearance point: a 59-minute cameo and a
    61-minute one differ by a point plus a clean-sheet chance.
    """

    cameo: np.ndarray
    start: np.ndarray

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "MinutesPool":
        minutes = frame["minutes"].dropna().to_numpy(dtype=float)
        cameo = minutes[(minutes > 0) & (minutes < 60)]
        start = minutes[minutes >= 60]
        return cls(
            cameo=cameo if len(cameo) else np.array([25.0]),
            start=start if len(start) else np.array([90.0]),
        )


@dataclass
class Bundle:
    """Everything the simulator needs for one frame of rows, already predicted.

    Rates are per 90 minutes; probabilities are conditional on a full
    appearance. Assembling this is ml/train_v3.py's job.
    """

    position: np.ndarray
    minutes_probs: np.ndarray  # (n, 3): out / cameo / start
    goals_rate: np.ndarray
    assists_rate: np.ndarray
    saves_rate: np.ndarray
    conceded_pmf: np.ndarray  # (n, K) P(team concedes k)
    p_dc: np.ndarray
    p_yellow: np.ndarray
    p_red: np.ndarray
    bonus_ranks: np.ndarray
    bonus_model: bonus_component.BonusModel
    scoring: Scoring
    minutes_pool: MinutesPool
    goals_alpha: np.ndarray | None = None
    assists_alpha: np.ndarray | None = None
    saves_alpha: np.ndarray | None = None
    #: hit-rate multiplier for a partial appearance, by minutes (see defcon)
    dc_minutes_scaling: dict = field(default_factory=dict)

    def slice(self, idx: np.ndarray) -> "Bundle":
        def take(v):
            return None if v is None else np.asarray(v)[idx]

        return Bundle(
            position=take(self.position),
            minutes_probs=self.minutes_probs[idx],
            goals_rate=take(self.goals_rate),
            assists_rate=take(self.assists_rate),
            saves_rate=take(self.saves_rate),
            conceded_pmf=self.conceded_pmf[idx],
            p_dc=take(self.p_dc),
            p_yellow=take(self.p_yellow),
            p_red=take(self.p_red),
            bonus_ranks=take(self.bonus_ranks),
            bonus_model=self.bonus_model,
            scoring=self.scoring,
            minutes_pool=self.minutes_pool,
            goals_alpha=take(self.goals_alpha),
            assists_alpha=take(self.assists_alpha),
            saves_alpha=take(self.saves_alpha),
            dc_minutes_scaling=self.dc_minutes_scaling,
        )


def _dc_scale(minutes: np.ndarray, scaling: dict) -> np.ndarray:
    """Empirical multiplier on P(defensive threshold) for a partial appearance.

    Defensive actions accumulate with time on the pitch and the threshold is
    high, so the chance of clearing it falls away much faster than linearly.
    The curve is measured from data (ml/components/defcon.fit_minutes_scaling)
    rather than assumed.
    """
    if not scaling:
        return np.clip(minutes / 90.0, 0.0, 1.0)
    edges = np.array(sorted(scaling), dtype=float)
    values = np.array([scaling[k] for k in sorted(scaling)], dtype=float)
    idx = np.clip(np.searchsorted(edges, minutes, side="right") - 1, 0, len(values) - 1)
    return values[idx]


def _simulate_chunk(
    bundle: Bundle, draws: int, rng: np.random.Generator
) -> np.ndarray:
    """(rows, draws) simulated points for one block of rows."""
    n = len(bundle.position)
    shape = (n, draws)
    position = bundle.position.reshape(-1, 1)

    # --- minutes class, then minutes ---
    cumulative = np.cumsum(bundle.minutes_probs, axis=1)
    u = rng.random(shape)
    klass = (u.reshape(n, draws, 1) > cumulative.reshape(n, 1, 3)).sum(axis=2)
    klass = np.clip(klass, 0, 2)

    minutes = np.zeros(shape)
    cameo_mask = klass == 1
    start_mask = klass == 2
    if cameo_mask.any():
        minutes[cameo_mask] = rng.choice(
            bundle.minutes_pool.cameo, size=int(cameo_mask.sum())
        )
    if start_mask.any():
        minutes[start_mask] = rng.choice(
            bundle.minutes_pool.start, size=int(start_mask.sum())
        )
    exposure = minutes / 90.0
    played = minutes > 0

    # --- attacking returns ---
    def counts(rate: np.ndarray, alpha: np.ndarray | None) -> np.ndarray:
        mu = rate.reshape(-1, 1) * exposure
        disp = (
            np.zeros(shape)
            if alpha is None
            else np.broadcast_to(alpha.reshape(-1, 1), shape)
        )
        return component_base.sample_counts(mu, disp, rng)

    goals = counts(bundle.goals_rate, bundle.goals_alpha)
    assists = counts(bundle.assists_rate, bundle.assists_alpha)
    saves = counts(bundle.saves_rate, bundle.saves_alpha)

    # --- team goals conceded, drawn once per fixture and shared ---
    k_values = np.arange(bundle.conceded_pmf.shape[1])
    cumulative_gc = np.cumsum(bundle.conceded_pmf, axis=1)
    u_gc = rng.random(shape)
    team_conceded = k_values[
        np.clip(
            (u_gc.reshape(n, draws, 1) > cumulative_gc.reshape(n, 1, -1)).sum(axis=2),
            0,
            len(k_values) - 1,
        )
    ]
    # a substitute is only exposed to the goals let in while he is on
    on_pitch_conceded = np.where(
        start_mask,
        team_conceded,
        rng.binomial(team_conceded, np.clip(exposure, 0.0, 1.0)),
    )
    clean_sheet = ((team_conceded == 0) & (minutes >= 60)).astype(float)

    # --- defensive contribution ---
    dc_prob = bundle.p_dc.reshape(-1, 1) * _dc_scale(minutes, bundle.dc_minutes_scaling)
    dc_hit = (rng.random(shape) < dc_prob) & played
    # scoring.points_from_components compares a count against the threshold, so
    # a hit is expressed as "exactly at the threshold"
    thresholds = np.zeros(5)
    for pos, value in scoring.DC_THRESHOLDS.items():
        thresholds[pos] = value
    dc_counts = dc_hit * thresholds[bundle.position].reshape(-1, 1)

    # --- discipline and bonus ---
    yellow = ((rng.random(shape) < bundle.p_yellow.reshape(-1, 1)) & played).astype(float)
    red = ((rng.random(shape) < bundle.p_red.reshape(-1, 1)) & played).astype(float)
    # bonus is conditioned on the returns drawn in this same iteration: a player
    # who just scored twice is near-certain to top the BPS table, and severing
    # that link visibly thins the haul tail
    bonus = (
        bonus_component.sample(
            bundle.bonus_model,
            bundle.bonus_ranks,
            bonus_component.returns_bucket(goals, assists),
            rng,
        )
        * played
    )

    return scoring.points_from_components(
        {
            "minutes": minutes,
            "goals_scored": goals,
            "assists": assists,
            "clean_sheets": clean_sheet,
            "goals_conceded": on_pitch_conceded,
            "saves": saves,
            "yellow_cards": yellow,
            "red_cards": red,
            "bonus": bonus,
            "defensive_contribution": dc_counts,
        },
        position,
        bundle.scoring,
    )


def _summarise(points: np.ndarray) -> dict[str, np.ndarray]:
    quantiles = np.quantile(points, [0.1, 0.5, 0.9], axis=1)
    return {
        "ev": points.mean(axis=1),
        "p_blank": (points <= BLANK).mean(axis=1),
        "p_return": (points >= RETURN).mean(axis=1),
        "p_haul": (points >= HAUL).mean(axis=1),
        "p10": quantiles[0],
        "p50": quantiles[1],
        "p90": quantiles[2],
    }


def simulate(
    frame: pd.DataFrame,
    bundle: Bundle,
    draws: int = DEFAULT_DRAWS,
    seed: int = DEFAULT_SEED,
    group_keys: tuple[str, ...] = ("player_code", "gameweek"),
) -> pd.DataFrame:
    """Simulate every row and summarise per player-gameweek.

    Returns one row per group in `group_keys` with the tail probabilities, the
    p10/p50/p90 quantiles, and two expectations:

      `ev`      the closed-form expectation from `analytic_ev`,
      `ev_mc`   the mean of the simulated draws.

    Both are kept because they fail differently. `ev_mc` is limited by the number
    of draws: a mean of integer point totals over 300 draws can only take values
    a third of a percent apart, which collapsed 29,000 predictions onto 1,700
    distinct values and cost 0.003 of rank correlation purely to ties. `ev` has
    no such granularity, so it is what gets ranked and stored. Their agreement is
    a test (tests/test_distribution.py) — a gap between them means the sampler
    and the scoring arithmetic have drifted apart.

    Rows sharing a group (a double gameweek) have their draws added together
    before any statistic is taken.
    """
    rng = np.random.default_rng(seed)
    frame = frame.reset_index(drop=True)
    codes, uniques = pd.factorize(
        pd.MultiIndex.from_frame(frame[list(group_keys)]), sort=True
    )
    order = np.argsort(codes, kind="stable")
    grouped_codes = codes[order]

    # chunk on group boundaries so a double gameweek is never split
    boundaries = np.flatnonzero(np.diff(grouped_codes)) + 1
    starts = [0]
    for b in boundaries:
        if b - starts[-1] >= CHUNK_ROWS:
            starts.append(int(b))
    starts.append(len(order))

    row_ev = analytic_ev(bundle)

    results: dict[int, dict[str, float]] = {}
    for begin, end in itertools.pairwise(starts):
        idx = order[begin:end]
        points = _simulate_chunk(bundle.slice(idx), draws, rng)
        chunk_codes = codes[idx]
        chunk_ev = row_ev[idx]
        for code in np.unique(chunk_codes):
            rows = chunk_codes == code
            totals = points[rows].sum(axis=0)
            stats = _summarise(totals.reshape(1, -1))
            results[int(code)] = {k: float(v[0]) for k, v in stats.items()}
            results[int(code)]["ev_mc"] = results[int(code)].pop("ev")
            results[int(code)]["ev"] = float(chunk_ev[rows].sum())

    out = pd.DataFrame.from_dict(results, orient="index").sort_index()
    keys = pd.MultiIndex.from_tuples(
        [uniques[i] for i in out.index], names=list(group_keys)
    )
    return out.set_index(keys).reset_index()


def _thinned_conceded_points(pmf: np.ndarray, exposure: float) -> np.ndarray:
    """E[floor(B / 2)] for B ~ Binomial(team goals conceded, `exposure`).

    A substitute is only exposed to the goals let in while he is on the pitch, so
    his share is thinned out of the team total *before* the every-second-goal
    step. Thinning afterwards (thinning the points rather than the goals) is not
    the same number: for a team that concedes two, a 30%-exposure substitute has
    a 9% chance of being on for both, not 30% of a point.
    """
    from scipy.stats import binom

    out = np.zeros(len(pmf))
    for total in range(pmf.shape[1]):
        conceded = np.arange(total + 1)
        expected = float(
            (
                binom.pmf(conceded, total, exposure)
                * (conceded // scoring.GOALS_CONCEDED_PER_POINT)
            ).sum()
        )
        out += pmf[:, total] * expected
    return out


def analytic_ev(bundle: Bundle) -> np.ndarray:
    """Closed-form expected points, used to check the simulator.

    Every term except saves and goals conceded is linear in a component mean, so
    it can be written down exactly; those two are step functions and are taken
    from their distributions. Agreement with `simulate` to Monte-Carlo error is
    a test (tests/test_distribution.py) — it is the cheapest way to catch a
    scoring or scaling mistake in the sampler.
    """
    sc = bundle.scoring
    pos = bundle.position
    p_cameo = bundle.minutes_probs[:, 1]
    p_start = bundle.minutes_probs[:, 2]

    cameo_exposure = bundle.minutes_pool.cameo.mean() / 90.0
    start_exposure = bundle.minutes_pool.start.mean() / 90.0
    exposure = p_cameo * cameo_exposure + p_start * start_exposure

    def lut(mapping: dict[int, int]) -> np.ndarray:
        arr = np.zeros(5)
        for k, v in mapping.items():
            arr[k] = v
        return arr[pos]

    ev = p_start * sc.long_play + p_cameo * sc.short_play
    ev = ev + lut(sc.goals) * bundle.goals_rate * exposure
    ev = ev + sc.assists * bundle.assists_rate * exposure

    p_cs = bundle.conceded_pmf[:, 0]
    ev = ev + lut(sc.clean_sheets) * p_cs * p_start

    # Goals conceded and saves are step functions of a count, so each has to be
    # evaluated *inside* a minutes class and then averaged by the class
    # probabilities. Evaluating once at `exposure` — which already folds in
    # P(play) — and multiplying by P(play) a second time shrinks the count before
    # a convex step and underprices the result. It cost keepers about 0.12 points
    # each while leaving every linear term untouched, so it showed up as v3
    # ranking keepers below outfielders rather than as an obvious error.
    k = np.arange(bundle.conceded_pmf.shape[1])
    conceded_full = (bundle.conceded_pmf * (k // scoring.GOALS_CONCEDED_PER_POINT)).sum(
        axis=1
    )
    ev = ev + lut(sc.goals_conceded) * (
        p_start * conceded_full
        + p_cameo * _thinned_conceded_points(bundle.conceded_pmf, cameo_exposure)
    )

    # saves pay per third save, so the mean is not enough
    from scipy.stats import poisson

    save_k = np.arange(0, 21)

    def save_points(class_exposure: float) -> np.ndarray:
        mu = bundle.saves_rate * max(class_exposure, 1e-9)
        return (
            poisson.pmf(save_k.reshape(1, -1), mu.reshape(-1, 1))
            * (save_k // scoring.SAVES_PER_POINT)
        ).sum(axis=1)

    ev = ev + sc.saves * (
        p_start * save_points(start_exposure) + p_cameo * save_points(cameo_exposure)
    )

    if sc.has_defensive_contribution:
        dc_scale_cameo = _dc_scale(
            np.full(1, bundle.minutes_pool.cameo.mean()), bundle.dc_minutes_scaling
        )[0]
        dc_scale_start = _dc_scale(
            np.full(1, bundle.minutes_pool.start.mean()), bundle.dc_minutes_scaling
        )[0]
        ev = ev + lut(sc.defensive_contribution) * bundle.p_dc * (
            p_start * dc_scale_start + p_cameo * dc_scale_cameo
        )

    played = p_start + p_cameo
    ev = ev + sc.yellow_cards * bundle.p_yellow * played
    ev = ev + sc.red_cards * bundle.p_red * played
    # Bonus turns on the returns drawn in the same appearance, and the rank
    # bucket maps to bonus non-linearly, so it marginalises per minutes class
    # for the same reason saves do.
    rows = len(bundle.position)
    ev = ev + sc.bonus * (
        p_start * bonus_expectation(bundle, np.full(rows, start_exposure))
        + p_cameo * bonus_expectation(bundle, np.full(rows, cameo_exposure))
    )
    return ev


def returns_probabilities(bundle: Bundle, exposure: np.ndarray) -> np.ndarray:
    """P(0), P(1), P(2+) goals-plus-assists, from the two rate components.

    Bonus depends on returns, so the analytic expectation has to marginalise over
    them. Poisson is used here regardless of the fitted family: the difference
    only shows in the far tail, and this path exists to cross-check the
    simulator, not to replace it.
    """
    from scipy.stats import poisson

    mu = (bundle.goals_rate + bundle.assists_rate) * np.maximum(exposure, 1e-9)
    p0 = poisson.pmf(0, mu)
    p1 = poisson.pmf(1, mu)
    return np.column_stack([p0, p1, np.clip(1.0 - p0 - p1, 0.0, 1.0)])


def bonus_expectation(bundle: Bundle, exposure: np.ndarray) -> np.ndarray:
    return bonus_component.expected_bonus(
        bundle.bonus_model, bundle.bonus_ranks, returns_probabilities(bundle, exposure)
    )
