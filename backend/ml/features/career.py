"""Multi-season player-class features (previous seasons only, never current)."""

import pandas as pd

FEATURES = [
    "prev_season_ppg",
    "ppg_prev2",
    "ppg_prev3",
    "pts_per90_prev1",
    "minutes_share_prev1",
    "starts_prev1",
    "seasons_in_pl",
    "age_years",
]

MINUTES_FLOOR = 900  # ignore bit-part seasons in multi-season averages
SEASON_MINUTES = 38 * 90.0


def season_totals(
    df: pd.DataFrame, value_cols: tuple[str, ...] = ()
) -> pd.DataFrame:
    """Per (player, season) totals over completed matches — the shared basis for
    the multi-season features here and for the previous-season priors in
    form_eb. Indexed by (player_code, start_year).

    `value_cols` are summed skipping nulls, and each gets a companion
    `<col>__minutes` holding the minutes played in the matches where that column
    was actually recorded, so a rate over a partially-recorded stat (xG before
    2022-23, defensive contributions before 2025-26) divides by the exposure it
    was observed over rather than by the whole season.
    """
    hist = df[~df["is_inference"]]
    named = {
        "pts": ("total_points", "sum"),
        "mins": ("minutes", "sum"),
        "games": ("total_points", "count"),
        "starts": ("minutes", lambda s: (s >= 60).sum()),
    }
    agg = hist.groupby(["player_code", "start_year"]).agg(**named)

    for col in value_cols:
        if col not in hist.columns:
            continue
        observed = hist[col].notna()
        extra = (
            hist.assign(
                _v=hist[col].where(observed, 0.0),
                _m=hist["minutes"].where(observed, 0.0),
            )
            .groupby(["player_code", "start_year"])
            .agg(**{col: ("_v", "sum"), f"{col}__minutes": ("_m", "sum")})
        )
        agg = agg.join(extra)
    return agg


def add(df: pd.DataFrame, birth_dates: pd.Series | None = None) -> pd.DataFrame:
    key = season_totals(df)

    def season_stat(col: str) -> dict:
        return key[col].to_dict()

    pts, mins, games, starts = (
        season_stat("pts"),
        season_stat("mins"),
        season_stat("games"),
        season_stat("starts"),
    )

    def trailing_ppg(code: int, year: int, span: int) -> float | None:
        p = m = g = 0
        for y in range(year - span, year):
            p += pts.get((code, y), 0)
            m += mins.get((code, y), 0)
            g += games.get((code, y), 0)
        if m < MINUTES_FLOOR or g == 0:
            return None
        return p / g

    pairs = list(zip(df["player_code"], df["start_year"]))
    df["prev_season_ppg"] = [
        pts.get((c, y - 1), 0) / games[(c, y - 1)] if (c, y - 1) in games else None
        for c, y in pairs
    ]
    df["ppg_prev2"] = [trailing_ppg(c, y, 2) for c, y in pairs]
    df["ppg_prev3"] = [trailing_ppg(c, y, 3) for c, y in pairs]
    df["pts_per90_prev1"] = [
        pts[(c, y - 1)] / max(mins[(c, y - 1)], 1) * 90 if (c, y - 1) in pts else None
        for c, y in pairs
    ]
    df["minutes_share_prev1"] = [
        mins[(c, y - 1)] / SEASON_MINUTES if (c, y - 1) in mins else None
        for c, y in pairs
    ]
    df["starts_prev1"] = [starts.get((c, y - 1)) for c, y in pairs]

    seen_years: dict[int, list[int]] = {}
    for code, year in pts:
        seen_years.setdefault(code, []).append(year)
    df["seasons_in_pl"] = [
        sum(1 for y2 in seen_years.get(c, []) if y2 < y) for c, y in pairs
    ]

    if birth_dates is not None:
        bd = pd.to_datetime(df["player_code"].map(birth_dates), utc=True)
        df["age_years"] = (df["kickoff_time"] - bd).dt.days / 365.25
    else:
        df["age_years"] = None
    return df
