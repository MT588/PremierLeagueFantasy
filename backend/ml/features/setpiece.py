"""Set-piece duty features (season-level orders from FPL data)."""

import pandas as pd

from ml.features.context import FeatureContext

FEATURES = ["pen_order", "is_pen_taker", "corner_duty", "fk_duty"]


def add(df: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    sp = ctx.setpiece.set_index(["season_id", "player_code"])
    keys = pd.MultiIndex.from_arrays([df["season_id"], df["player_code"]])
    matched = sp.reindex(keys)
    df["pen_order"] = matched["penalties_order"].to_numpy()
    df["is_pen_taker"] = (matched["penalties_order"].to_numpy() == 1).astype(float)
    df["corner_duty"] = (matched["corners_order"].fillna(9).to_numpy() <= 2).astype(
        float
    )
    df["fk_duty"] = (matched["freekicks_order"].fillna(9).to_numpy() <= 2).astype(float)
    return df
