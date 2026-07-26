"""Generate v2 predictions with minutes probabilities and drivers."""

import argparse
import logging

import lightgbm as lgb
import pandas as pd
from sqlalchemy import text

from app.db import engine
from ml import explain, points_model
from ml.features import FEATURES, build_inference_frame
from ml.minutes_model import predict_proba
from ml.train_v2 import ARTIFACTS, MODEL_VERSION, coerce_features
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

RATING_BUCKETS = [(0.90, "excellent"), (0.65, "good"), (0.35, "average"), (0.0, "poor")]


def current_season_and_next_gws(horizon: int) -> tuple[int, list[int]]:
    with engine.connect() as conn:
        season_id = conn.execute(text("select id from seasons where is_current")).scalar_one()
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
        log.warning("no upcoming gameweeks for the current season")
        return 0
    log.info("predicting season_id=%d gameweeks=%s (%s)", season_id, gws, MODEL_VERSION)

    frame = coerce_features(build_inference_frame(engine, season_id, gws))
    frame = frame.reset_index(drop=True)

    mmodel = lgb.Booster(model_file=str(ARTIFACTS / f"model_minutes_{MODEL_VERSION}.txt"))
    pmodel = lgb.Booster(model_file=str(ARTIFACTS / f"model_points_{MODEL_VERSION}.txt"))
    cameo = points_model.load_cameo(ARTIFACTS / f"cameo_means_{MODEL_VERSION}.json")

    mprobs = predict_proba(mmodel, frame)
    ppred = pmodel.predict(frame[FEATURES]).clip(min=0)
    frame["predicted_points"] = points_model.combine(
        ppred, mprobs, frame["position"], cameo
    ).clip(min=0)
    frame["p_start"] = mprobs[:, 2]
    frame["p_cameo"] = mprobs[:, 1]
    frame["drivers"] = explain.drivers_for(pmodel, frame, mprobs, ppred)

    # availability gate: injured/suspended/unavailable players score ~0
    gated = (frame["status"] != "a") & (frame["chance_of_playing"].fillna(100) < 75)
    frame.loc[gated, "predicted_points"] = 0.0
    frame.loc[gated, "p_start"] = 0.0
    frame.loc[gated, "drivers"] = frame.loc[gated, "drivers"].map(
        lambda d: {**d, "gated": True}
    )

    # double gameweeks: sum points across fixtures, keep the first fixture's drivers
    frame = frame.sort_values(["player_code", "gameweek", "kickoff_time"])
    agg = frame.groupby(["player_code", "gameweek", "position"], as_index=False).agg(
        predicted_points=("predicted_points", "sum"),
        predicted_minutes=("minutes_avg_5", "mean"),
        p_start=("p_start", "max"),
        p_cameo=("p_cameo", "max"),
        drivers=("drivers", "first"),
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
            "p_start": round(float(r.p_start), 3),
            "p_cameo": round(float(r.p_cameo), 3),
            "drivers": r.drivers,
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
