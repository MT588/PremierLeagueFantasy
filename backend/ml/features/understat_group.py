"""Understat-based features: shot-quality rates and cross-league career for
new signings, plus xG backfill for 2021-22 (FPL has no xG that season)."""

import pandas as pd

from ml.features.context import FeatureContext

FEATURES = [
    "ust_npxg90_5", "ust_xa90_5", "ust_shots90_5", "ust_kp90_5", "ust_npxg90_20",
    "ust_career_npxg90_adj", "ust_career_xa90_adj", "ust_career_minutes_adj",
    "ust_prev_league_coef",
]


def backfill_2021_xg(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    """Fill missing FPL xG columns (2021-22) from Understat EPL matches joined
    on (player, kickoff date). Runs BEFORE the form group so xg90_* windows
    benefit."""
    need = df["expected_goals"].isna() & ~df["is_inference"]
    if not need.any():
        return df
    ust = ctx.understat[ctx.understat["league"] == "EPL"].copy()
    ust["match_day"] = ust["match_date"].dt.date
    lookup = ust.set_index(["player_code", "match_day"])[["xg", "xa"]]
    lookup = lookup[~lookup.index.duplicated()]

    days = df["kickoff_time"].dt.date
    keys = pd.MultiIndex.from_arrays([df["player_code"], days])
    matched = lookup.reindex(keys)
    fill_mask = need.to_numpy() & matched["xg"].notna().to_numpy()
    df.loc[fill_mask, "expected_goals"] = matched["xg"].to_numpy()[fill_mask]
    df.loc[fill_mask, "expected_assists"] = matched["xa"].to_numpy()[fill_mask]
    df.loc[fill_mask, "expected_goal_involvements"] = (
        matched["xg"].to_numpy()[fill_mask] + matched["xa"].to_numpy()[fill_mask]
    )
    return df


def _rolling_rates(ust: pd.DataFrame) -> pd.DataFrame:
    """Per (player, match_date): trailing rates inclusive of that match, to be
    joined as-of strictly before each FPL kickoff."""
    ust = ust.sort_values(["player_code", "match_date"]).reset_index(drop=True)
    g = ust.groupby("player_code", sort=False)
    out = ust[["player_code", "match_date"]].copy()
    for w in (5, 20):
        mins = g["minutes"].transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
        out[f"npxg90_{w}"] = (
            g["npxg"].transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
            / mins.clip(lower=1) * 90
        )
        if w == 5:
            for col, name in (("xa", "xa90_5"), ("shots", "shots90_5"), ("key_passes", "kp90_5")):
                out[name] = (
                    g[col].transform(lambda s: s.rolling(5, min_periods=1).sum())
                    / mins.clip(lower=1) * 90
                )
    return out


def add(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    ust = ctx.understat
    if ust.empty:
        for f in FEATURES:
            df[f] = None
        return df

    rates = _rolling_rates(ust)
    rates = rates.sort_values("match_date")
    order = df.index
    left = df[["player_code", "kickoff_time"]].reset_index().sort_values("kickoff_time")
    left = left.dropna(subset=["kickoff_time"])
    merged = pd.merge_asof(
        left,
        rates.rename(columns={"match_date": "kickoff_time"}),
        on="kickoff_time",
        by="player_code",
        direction="backward",
        allow_exact_matches=False,
    ).set_index("index")
    for src, dst in (
        ("npxg90_5", "ust_npxg90_5"), ("xa90_5", "ust_xa90_5"),
        ("shots90_5", "ust_shots90_5"), ("kp90_5", "ust_kp90_5"),
        ("npxg90_20", "ust_npxg90_20"),
    ):
        df[dst] = merged[src].reindex(order)

    # cross-league career (trailing 2 understat seasons), league-coef weighted
    coefs = ctx.league_coefs
    ust2 = ust.copy()
    ust2["coef"] = [
        coefs.get((lg, s), 0.75 if lg != "EPL" else 1.0)
        for lg, s in zip(ust2["league"], ust2["season"])
    ]
    per_season = (
        ust2.groupby(["player_code", "season"])
        .agg(
            npxg_adj=("npxg", "sum"), xa_adj=("xa", "sum"),
            mins=("minutes", "sum"), coef=("coef", "mean"),
        )
        .reset_index()
    )
    per_season["npxg_adj"] *= per_season["coef"]
    per_season["xa_adj"] *= per_season["coef"]
    key = per_season.set_index(["player_code", "season"])

    def career(code: int, year: int) -> tuple:
        npxg = xa = mins = 0.0
        coef = None
        for y in (year - 1, year - 2):
            if (code, y) in key.index:
                row = key.loc[(code, y)]
                npxg += row["npxg_adj"]
                xa += row["xa_adj"]
                mins += row["mins"]
                if coef is None:
                    coef = row["coef"]
        if mins < 450:
            return None, None, None, coef
        return npxg / mins * 90, xa / mins * 90, mins, coef

    vals = [career(c, y) for c, y in zip(df["player_code"], df["start_year"])]
    df["ust_career_npxg90_adj"] = [v[0] for v in vals]
    df["ust_career_xa90_adj"] = [v[1] for v in vals]
    df["ust_career_minutes_adj"] = [v[2] for v in vals]
    df["ust_prev_league_coef"] = [v[3] for v in vals]
    return df
