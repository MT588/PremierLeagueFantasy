"""Sample-size-aware form: current-season rates shrunk toward a player prior.

The naive rolling windows in form.py are the model's strongest features and its
weakest link in August: `points_avg_5` after one match is one match, and for a
new signing it is nothing at all. This group replaces "last 5" with an
empirical-Bayes blend,

    shrunk = w * current_season_rate + (1 - w) * prior,   w = n / (n + k)

where `n` is how much the player has actually played *this* season (matches for
per-game stats, 90s for per-90 rates) and the prior is built from the deepest
history available:

    1. the same rate last season,
    2. the trailing two-season career rate,
    3. Understat's cross-league career rate (new signings from abroad),
    4. a position x price-bucket league prior, computed only from seasons
       strictly before the row's own — so it stays leakage-safe.

`k` is not hand-picked: ml/shrinkage.py fits one per statistic on training-fold
seasons, which is why `add` only computes the blend's ingredients and `apply`
finishes the job. Refitting a fold is then a cheap vectorised recompute rather
than a full frame rebuild.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.features.career import season_totals
from ml.features.context import FeatureContext


@dataclass(frozen=True)
class Stat:
    """One shrunk statistic. `per` is "90" for rates and "game" for per-match
    means; `default_k` is used until shrinkage.fit_ks supplies a fitted value."""

    name: str
    col: str
    per: str
    default_k: float
    understat_prior: str | None = None


STATS: tuple[Stat, ...] = (
    Stat("points_pg", "total_points", "game", 6.0),
    Stat("minutes", "minutes", "game", 4.0),
    Stat("start_share", "_eb_started", "game", 4.0),
    Stat("goals90", "goals_scored", "90", 8.0, "ust_career_npxg90_adj"),
    Stat("assists90", "assists", "90", 8.0, "ust_career_xa90_adj"),
    Stat("xg90", "expected_goals", "90", 6.0, "ust_career_npxg90_adj"),
    Stat("xa90", "expected_assists", "90", 6.0, "ust_career_xa90_adj"),
    Stat("xgi90", "expected_goal_involvements", "90", 6.0),
    Stat("bps", "bps", "game", 5.0),
    Stat("dc90", "defensive_contribution", "90", 6.0),
    # inputs to the defensive-contribution and discipline components; recorded
    # from 2025-26 only, so null for earlier seasons
    Stat("tackles90", "tackles", "90", 6.0),
    Stat("cbi90", "clearances_blocks_interceptions", "90", 6.0),
    Stat("recoveries90", "recoveries", "90", 6.0),
    Stat("yellows90", "yellow_cards", "90", 10.0),
    Stat("saves90", "saves", "90", 6.0),
)

# The shipped group. The component-specific rates below are deliberately left
# out: they are null for most of the archive and only the model that needs them
# should carry that sparsity.
FEATURES: list[str] = [
    *[
        f"eb_{s.name}"
        for s in STATS
        if s.name
        not in ("tackles90", "cbi90", "recoveries90", "yellows90", "saves90")
    ],
    "games_played_season",
    "minutes90_season",
    "eb_weight_cur",
    "is_new_to_club",
]

# Consumed by ml/components/defcon.py
DC_FEATURES: list[str] = ["eb_dc90", "eb_tackles90", "eb_cbi90", "eb_recoveries90"]
# Consumed by ml/components/discipline.py. `suspension_gap` is how many bookings
# the player is from the next ban (5, 10 or 15 in a season): a player on four is
# a player his manager may rest, and one on the brink plays more cautiously.
DISCIPLINE_FEATURES: list[str] = [
    "eb_yellows90",
    "yellows_season",
    "suspension_gap",
]
# Consumed by ml/components/saves.py
SAVES_FEATURES: list[str] = ["eb_saves90"]

SUSPENSION_THRESHOLDS = (5, 10, 15)

# Price buckets in FPL's 0.1m units, for the position x price league prior.
PRICE_BINS = (0, 45, 55, 65, 80, 100, 1000)

DEFAULT_KS: dict[str, float] = {s.name: s.default_k for s in STATS}


def _cur(name: str) -> str:
    return f"_eb_cur_{name}"


def _prior(name: str) -> str:
    return f"_eb_prior_{name}"


def _n(name: str) -> str:
    return f"_eb_n_{name}"


def _suspension_gap(yellows: float) -> float:
    """Bookings remaining before the next automatic ban. Past the last
    threshold there is nothing left to accumulate toward, so the gap opens up."""
    if pd.isna(yellows):
        return np.nan
    for threshold in SUSPENSION_THRESHOLDS:
        if yellows < threshold:
            return float(threshold - yellows)
    return float(len(SUSPENSION_THRESHOLDS) + 1)


def _current_season_rate(
    df: pd.DataFrame, stat: Stat
) -> tuple[pd.Series, pd.Series]:
    """(rate so far this season, exposure), both strictly before this match.

    Exposure counts only matches where the statistic was actually recorded, so
    a rate is never diluted by seasons in which the stat did not exist.
    """
    values = df[stat.col]
    observed = values.notna()
    keys = [df["player_code"], df["season_id"]]

    def lagged_cumsum(series: pd.Series) -> pd.Series:
        return series.groupby(keys, sort=False).transform(
            lambda s: s.shift(1).cumsum()
        )

    num = lagged_cumsum(values.where(observed, 0.0))
    weight = (
        df["minutes"].where(observed, 0.0)
        if stat.per == "90"
        else observed.astype(float)
    )
    den = lagged_cumsum(weight)
    scale = 90.0 if stat.per == "90" else 1.0
    exposure = den / scale
    rate = num / den.where(den > 0) * scale
    return rate, exposure


def _previous_season_rate(df: pd.DataFrame, stat: Stat) -> pd.Series:
    """The same rate over the player's previous season, then over the two
    seasons before that if the previous one is too thin to trust."""
    totals = season_totals(df, value_cols=(stat.col,))
    if stat.col not in totals.columns:
        return pd.Series(np.nan, index=df.index)

    if stat.per == "90":
        num, den = totals[stat.col], totals[f"{stat.col}__minutes"] / 90.0
    else:
        num, den = totals[stat.col], totals["games"].astype(float)
    rate = (num / den.where(den > 0)).rename("rate")
    exposure = den.rename("exposure")

    lookup = rate.to_dict()
    exposures = exposure.to_dict()
    pairs = list(zip(df["player_code"], df["start_year"]))

    def trailing(code: int, year: int) -> float:
        """Previous season if it carries enough exposure, else pool the two
        seasons before it."""
        one = lookup.get((code, year - 1))
        if one is not None and not pd.isna(one) and exposures.get((code, year - 1), 0) >= 5:
            return one
        pooled_num = pooled_den = 0.0
        for back in (1, 2, 3):
            key = (code, year - back)
            if key in lookup and not pd.isna(lookup[key]):
                pooled_num += lookup[key] * exposures[key]
                pooled_den += exposures[key]
        if pooled_den >= 2:
            return pooled_num / pooled_den
        return one if one is not None else np.nan

    return pd.Series([trailing(c, y) for c, y in pairs], index=df.index)


def _league_prior(df: pd.DataFrame, stat: Stat, rate: pd.Series) -> pd.Series:
    """Position x price-bucket mean of `rate`, over seasons strictly earlier than
    the row's own. The last resort for players with no usable history."""
    bucket = pd.cut(df["value"], bins=list(PRICE_BINS), labels=False, right=False)
    frame = pd.DataFrame(
        {
            "year": df["start_year"],
            "position": df["position"],
            "bucket": bucket,
            "rate": rate,
            "is_hist": ~df["is_inference"],
        }
    )
    observed = frame[frame["is_hist"] & frame["rate"].notna()]
    per_year = observed.groupby(["year", "position", "bucket"])["rate"].agg(
        ["sum", "count"]
    )
    per_pos_year = observed.groupby(["year", "position"])["rate"].agg(["sum", "count"])

    # cumulative over previous years -> a prior that never sees its own season
    cum: dict[tuple, tuple[float, float]] = {}
    running: dict[tuple, tuple[float, float]] = {}
    for year in sorted(frame["year"].dropna().unique()):
        for key, (s, c) in list(running.items()):
            cum[(year, *key)] = (s, c)
        for (y, pos, buck), row in per_year.iterrows():
            if y != year:
                continue
            prev = running.get((pos, buck), (0.0, 0.0))
            running[(pos, buck)] = (prev[0] + row["sum"], prev[1] + row["count"])
        for (y, pos), row in per_pos_year.iterrows():
            if y != year:
                continue
            prev = running.get((pos,), (0.0, 0.0))
            running[(pos,)] = (prev[0] + row["sum"], prev[1] + row["count"])

    def lookup(year: float, pos: float, buck: float) -> float:
        for key in ((year, pos, buck), (year, pos)):
            hit = cum.get(key)
            if hit and hit[1] >= 20:
                return hit[0] / hit[1]
        return np.nan

    return pd.Series(
        [
            lookup(y, p, b)
            for y, p, b in zip(frame["year"], frame["position"], frame["bucket"])
        ],
        index=df.index,
    )


def add(df: pd.DataFrame, ctx: FeatureContext | None = None) -> pd.DataFrame:
    """Compute the blend ingredients, then apply the default weights. Runs after
    the understat group so it can borrow cross-league career rates as priors."""
    df["_eb_started"] = (df["minutes"] >= 60).astype(float).where(df["minutes"].notna())

    built: dict[str, pd.Series] = {}
    for stat in STATS:
        if stat.col not in df.columns:
            built[_cur(stat.name)] = pd.Series(np.nan, index=df.index)
            built[_prior(stat.name)] = pd.Series(np.nan, index=df.index)
            built[_n(stat.name)] = pd.Series(0.0, index=df.index)
            continue
        rate, exposure = _current_season_rate(df, stat)
        prior = _previous_season_rate(df, stat)

        if stat.understat_prior and stat.understat_prior in df.columns:
            prior = prior.fillna(pd.to_numeric(df[stat.understat_prior], errors="coerce"))
        prior = prior.fillna(_league_prior(df, stat, rate))

        built[_cur(stat.name)] = rate
        built[_prior(stat.name)] = prior
        built[_n(stat.name)] = exposure.fillna(0.0)

    built["games_played_season"] = (
        df.groupby(["player_code", "season_id"], sort=False).cumcount().astype(float)
    )
    # goals90's exposure is plain minutes played (goals are recorded every
    # season), so it doubles as the season's 90s-played count.
    built["minutes90_season"] = built[_n("goals90")]

    # A player whose club changed since his last appearance has no useful
    # current-team context, which is exactly when the prior should dominate.
    prev_team = df.groupby("player_code", sort=False)["team_code"].transform(
        lambda s: s.shift(1)
    )
    built["is_new_to_club"] = (
        prev_team.notna() & (prev_team != df["team_code"])
    ).astype(float)

    # Bookings accumulated earlier this season, and the gap to the next ban.
    yellows = (
        df["yellow_cards"]
        .fillna(0.0)
        .groupby([df["player_code"], df["season_id"]], sort=False)
        .transform(lambda s: s.shift(1).cumsum())
    )
    built["yellows_season"] = yellows
    built["suspension_gap"] = yellows.map(_suspension_gap)

    # `_eb_started` stays on the frame: it is start_share's target, which
    # ml/shrinkage.py needs when it fits that statistic's weight.
    df = pd.concat([df, pd.DataFrame(built, index=df.index)], axis=1)
    return apply(df, DEFAULT_KS)


def apply(df: pd.DataFrame, ks: dict[str, float] | None = None) -> pd.DataFrame:
    """Blend the ingredients with shrinkage weights. Cheap and idempotent, so a
    fold can refit `ks` and recompute without rebuilding the frame."""
    ks = {**DEFAULT_KS, **(ks or {})}
    computed: dict[str, np.ndarray] = {}
    for stat in STATS:
        k = float(ks[stat.name])
        n = df[_n(stat.name)].fillna(0.0)
        cur = df[_cur(stat.name)]
        prior = df[_prior(stat.name)]
        w = n / (n + k)
        # With only one side available, lean fully on it rather than letting a
        # null swallow the feature.
        blended = w * cur.fillna(0.0) + (1 - w) * prior.fillna(0.0)
        computed[f"eb_{stat.name}"] = np.where(
            cur.isna() & prior.isna(),
            np.nan,
            np.where(cur.isna(), prior, np.where(prior.isna(), cur, blended)),
        )
    n_pts = df[_n("points_pg")].fillna(0.0)
    computed["eb_weight_cur"] = (n_pts / (n_pts + float(ks["points_pg"]))).to_numpy()

    frame = pd.DataFrame(computed, index=df.index)
    return pd.concat([df.drop(columns=frame.columns, errors="ignore"), frame], axis=1)
