"""Generate predictions for the next unfinished gameweeks and upsert them."""

import argparse
import logging

import lightgbm as lgb
import pandas as pd
from sqlalchemy import text

from app.db import engine
from ml.features import FEATURES, build_inference_frame
from ml.train import ARTIFACTS, MODEL_VERSION
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

RATING_BUCKETS = [(0.90, "excellent"), (0.65, "good"), (0.35, "average"), (0.0, "poor")]


def current_season_and_next_gws(horizon: int) -> tuple[int, list[int]]:
    with engine.connect() as conn:
        season_id = conn.execute(
            text("select id from seasons where is_current")
        ).scalar_one()
        gws = (
            conn.execute(
                text(
                    "select distinct gameweek from fixtures "
                    "where season_id = :sid and not finished and gameweek is not null "
                    "order by gameweek limit :n"
                ),
                {"sid": season_id, "n": horizon},
            )
            .scalars()
            .all()
        )
    return season_id, list(gws)


def assign_ratings(df: pd.DataFrame) -> pd.Series:
    def bucket(group: pd.Series) -> pd.Series:
        ranks = group.rank(pct=True)
        out = pd.Series("poor", index=group.index)
        for cutoff, label in RATING_BUCKETS:
            out[ranks >= cutoff] = label
            ranks = ranks.mask(ranks >= cutoff)
        return out

    return df.groupby(["gameweek", "position"])["predicted_points"].transform(bucket)


def run(horizon: int = 5) -> int:
    season_id, gws = current_season_and_next_gws(horizon)
    if not gws:
        log.warning("no upcoming gameweeks found for current season")
        return 0
    log.info("predicting season_id=%d gameweeks=%s", season_id, gws)

    frame = build_inference_frame(engine, season_id, gws)
    model = lgb.Booster(model_file=str(ARTIFACTS / f"model_{MODEL_VERSION}.txt"))
    frame["predicted_points"] = model.predict(
        frame[FEATURES], num_iteration=model.best_iteration
    ).clip(min=0)
    frame["predicted_minutes"] = frame["minutes_avg_5"]

    # availability gate: injured/suspended/unavailable players score ~0
    gated = (frame["status"] != "a") & (frame["chance_of_playing"].fillna(100) < 75)
    frame.loc[gated, "predicted_points"] = 0.0

    # double gameweeks: sum per-fixture predictions per (player, gameweek)
    agg = (
        frame.groupby(["player_code", "gameweek", "position"], as_index=False)
        .agg(predicted_points=("predicted_points", "sum"),
             predicted_minutes=("predicted_minutes", "mean"))
    )
    agg["rating"] = assign_ratings(agg)

    rows = [
        {
            "season_id": season_id,
            "player_code": int(r.player_code),
            "gameweek": int(r.gameweek),
            "predicted_points": round(float(r.predicted_points), 3),
            "predicted_minutes": None if pd.isna(r.predicted_minutes)
            else round(float(r.predicted_minutes), 1),
            "rating": r.rating,
            "model_version": MODEL_VERSION,
        }
        for r in agg.itertuples()
    ]
    n = upsert(engine, "predictions", rows,
               ["season_id", "player_code", "gameweek", "model_version"])
    log.info("wrote %d predictions", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=5)
    args = parser.parse_args()
    run(args.horizon)
