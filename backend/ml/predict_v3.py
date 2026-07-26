"""Write v3 predictions: expected points, the distribution around them, drivers.

Mirrors ml/predict_v2.py and keeps its behaviour where it still applies — the
availability gate, the rating buckets, one row per player-gameweek — while adding
the distributional columns and swapping the driver payload from feature
attributions to the component breakdown.

Double gameweeks are handled inside ml/distribution.simulate, which adds the
per-fixture draws before summarising; the old approach of summing the point
predictions cannot produce a coherent p90.

    uv run python -m ml.predict_v3 --horizon 5
"""

import argparse
import logging

import pandas as pd
from sqlalchemy import text

from app.constants import MODEL_VERSION
from app.db import engine
from ml import scoring
from ml.components import team_defence
from ml.distribution import simulate
from ml.features import build_inference_frame
from ml.features.context import load_context
from ml.train_v2 import coerce_features
from ml.train_v3 import ARTIFACTS
from ml.v3_model import V3Model, apply_shrinkage
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

RATING_BUCKETS = [(0.90, "excellent"), (0.65, "good"), (0.35, "average"), (0.0, "poor")]
DRAWS = 4000
# How many components to name in the driver payload.
TOP_COMPONENTS = 4


def current_season_and_next_gws(horizon: int) -> tuple[int, list[int], str]:
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
        season_name = conn.execute(
            text("select name from seasons where id = :sid"), {"sid": season_id}
        ).scalar_one()
    return season_id, list(gws), season_name


def assign_ratings(df: pd.DataFrame) -> pd.Series:
    def bucket(group: pd.Series) -> pd.Series:
        ranks = group.rank(pct=True)
        out = pd.Series("poor", index=group.index)
        for cutoff, label in RATING_BUCKETS:
            out[ranks >= cutoff] = label
            ranks = ranks.mask(ranks >= cutoff)
        return out

    return df.groupby(["gameweek", "position"])["predicted_points"].transform(bucket)


def build_drivers(
    frame: pd.DataFrame, components: pd.DataFrame, distribution: pd.DataFrame
) -> dict[tuple[int, int], dict]:
    """One driver payload per player-gameweek.

    v2 explained a prediction with SHAP attributions over 76 features. v3 can do
    something more direct: the expected points *are* a sum of priced components,
    so the explanation is that sum — "5.9 points, of which 2.4 is goal threat and
    1.6 a clean sheet" — with the dominant components named. The shape keeps v2's
    keys so the existing UI panel continues to work.
    """
    names = list(components.columns)
    ranked = components.assign(
        player_code=frame["player_code"].to_numpy(), gameweek=frame["gameweek"].to_numpy()
    )
    grouped = ranked.groupby(["player_code", "gameweek"], as_index=False)[names].sum()
    dist = distribution.set_index(["player_code", "gameweek"])

    out: dict[tuple[int, int], dict] = {}
    for row in grouped.itertuples(index=False):
        values = {name: float(getattr(row, name)) for name in names}
        key = (int(row.player_code), int(row.gameweek))
        top = sorted(values.items(), key=lambda kv: -abs(kv[1]))[:TOP_COMPONENTS]
        summary = dist.loc[key] if key in dist.index else None
        out[key] = {
            "components": [
                {"name": name, "points": round(value, 3)}
                for name, value in top
                if abs(value) > 0.01
            ],
            "p_start": round(float(summary["p_start"]), 3) if summary is not None else None,
            "p_cameo": round(float(summary["p_cameo"]), 3) if summary is not None else None,
            "expected_if_start": round(sum(values.values()), 2),
        }
    return out


def run(horizon: int = 5, draws: int = DRAWS) -> int:
    season_id, gws, season_name = current_season_and_next_gws(horizon)
    if not gws:
        log.warning("no upcoming gameweeks for the current season")
        return 0
    log.info(
        "predicting season_id=%d gameweeks=%s (%s, %d draws)",
        season_id,
        gws,
        MODEL_VERSION,
        draws,
    )

    model = V3Model.load(ARTIFACTS, MODEL_VERSION)
    ctx = load_context(engine)
    frame = build_inference_frame(engine, season_id, gws)
    frame = coerce_features(apply_shrinkage(frame, model.shrinkage_ks)).reset_index(
        drop=True
    )

    team_frame = team_defence.build_team_frame(engine, ctx)
    team_frame = team_frame[team_frame["season_id"] == season_id]
    lam = model.team.predict(team_frame)
    team_pred = team_frame[["season_id", "fpl_fixture_id", "team_code"]].assign(
        lambda_conceded=lam["conceded"], lambda_scored=lam["scored"]
    )

    season_scoring = scoring.for_season(season_name)
    bundle = model.build_bundle(frame, team_pred, season_scoring)
    distribution = simulate(frame, bundle, draws=draws)

    # minutes probabilities are per fixture; a double gameweek reports the best
    starts = (
        frame.assign(
            p_start=bundle.minutes_probs[:, 2], p_cameo=bundle.minutes_probs[:, 1]
        )
        .groupby(["player_code", "gameweek"], as_index=False)
        .agg(
            p_start=("p_start", "max"),
            p_cameo=("p_cameo", "max"),
            predicted_minutes=("eb_minutes", "mean"),
            position=("position", "first"),
        )
    )
    out = distribution.merge(starts, on=["player_code", "gameweek"], how="left")

    components = model.component_evs(frame, bundle)
    drivers = build_drivers(frame, components, out)

    out["upside"] = out["ev"] + model.upside_lambda * out["p_haul"]
    out["predicted_points"] = out["ev"].clip(lower=0)

    # availability gate: injured, suspended or unavailable players score nothing.
    # Kept identical to v2 — player_seasons.status is a season-end snapshot for
    # historical seasons, so it can only ever be an inference-time gate.
    availability = (
        frame.groupby(["player_code", "gameweek"], as_index=False)
        .agg(status=("status", "first"), chance=("chance_of_playing", "first"))
    )
    out = out.merge(availability, on=["player_code", "gameweek"], how="left")
    gated = (out["status"] != "a") & (out["chance"].fillna(100) < 75)
    for column in (
        "predicted_points",
        "upside",
        "p_start",
        "p_return",
        "p_haul",
        "p10",
        "p50",
        "p90",
        "ev",
    ):
        out.loc[gated, column] = 0.0
    out.loc[gated, "p_blank"] = 1.0

    out["rating"] = assign_ratings(out)
    gated_keys = {
        (int(p), int(g))
        for p, g in zip(out.loc[gated, "player_code"], out.loc[gated, "gameweek"])
    }

    rows = []
    for r in out.itertuples():
        key = (int(r.player_code), int(r.gameweek))
        driver = dict(drivers.get(key, {}))
        if key in gated_keys:
            driver["gated"] = True
        rows.append(
            {
                "season_id": season_id,
                "player_code": int(r.player_code),
                "gameweek": int(r.gameweek),
                "predicted_points": round(float(r.predicted_points), 3),
                "predicted_minutes": None
                if pd.isna(r.predicted_minutes)
                else round(float(r.predicted_minutes), 1),
                "p_start": round(float(r.p_start), 3),
                "p_cameo": round(float(r.p_cameo), 3),
                "p_blank": round(float(r.p_blank), 3),
                "p_return": round(float(r.p_return), 3),
                "p_haul": round(float(r.p_haul), 3),
                "p10": round(float(r.p10), 2),
                "p50": round(float(r.p50), 2),
                "p90": round(float(r.p90), 2),
                "upside": round(float(r.upside), 3),
                "components": driver.get("components"),
                "drivers": driver,
                "rating": r.rating,
                "model_version": MODEL_VERSION,
            }
        )
    n = upsert(
        engine,
        "predictions",
        rows,
        ["season_id", "player_code", "gameweek", "model_version"],
    )
    log.info("wrote %d predictions", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--draws", type=int, default=DRAWS)
    args = parser.parse_args()
    run(args.horizon, args.draws)
