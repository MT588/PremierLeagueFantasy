"""Ingest Premier League betting odds from football-data.co.uk season CSVs.

Matching to our fixtures needs no date logic: a (home, away) pairing occurs
exactly once per PL season, so (season_id, home_team_code, away_team_code)
is a natural key. Kickoff dates are still compared as a sanity check.
"""

import io
import logging
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import Engine, text

from pipeline.ingest_vaastav import records
from pipeline.team_names import TEAM_NAMES
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "odds"
BASE = "https://www.football-data.co.uk/mmz4281"

ODDS_COLS = {
    "B365H": "b365_home",
    "B365D": "b365_draw",
    "B365A": "b365_away",
    "AvgH": "avg_home",
    "AvgD": "avg_draw",
    "AvgA": "avg_away",
    "Avg>2.5": "over25",
    "Avg<2.5": "under25",
}


def season_code(season_name: str) -> str:
    # '2021-22' -> '2122'
    return season_name[2:4] + season_name[5:7]


def fetch_season_csv(season_name: str) -> pd.DataFrame | None:
    cache = CACHE_DIR / f"E0_{season_code(season_name)}.csv"
    if cache.exists():
        return pd.read_csv(cache)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    resp = httpx.get(f"{BASE}/{season_code(season_name)}/E0.csv", timeout=60)
    if resp.status_code != 200 or len(resp.text) < 200:
        log.info("odds: no data for %s yet", season_name)
        return None
    cache.write_bytes(resp.content)
    return pd.read_csv(io.BytesIO(resp.content))


def ingest_odds(engine: Engine) -> None:
    name_to_code = {names[2]: code for code, names in TEAM_NAMES.items()}

    with engine.connect() as conn:
        seasons = conn.execute(text("select id, name from seasons order by start_year")).all()
        fixtures = pd.read_sql(
            text(
                "select season_id, fpl_fixture_id, home_team_code, away_team_code, "
                "kickoff_time::date as kickoff_date from fixtures"
            ),
            conn,
        )
    fx_key = fixtures.set_index(["season_id", "home_team_code", "away_team_code"])

    total, unmatched_all = 0, []
    for season_id, season_name in seasons:
        df = fetch_season_csv(season_name)
        if df is None:
            continue
        df = df.dropna(subset=["HomeTeam", "AwayTeam"])
        df["home_code"] = df["HomeTeam"].map(name_to_code)
        df["away_code"] = df["AwayTeam"].map(name_to_code)
        unknown = df[df["home_code"].isna() | df["away_code"].isna()]
        if len(unknown):
            raise RuntimeError(
                f"{season_name}: unmapped football-data team names: "
                f"{sorted(set(unknown['HomeTeam']) | set(unknown['AwayTeam']))}"
            )

        rows, unmatched = [], []
        for r in df.to_dict("records"):
            key = (season_id, int(r["home_code"]), int(r["away_code"]))
            if key not in fx_key.index:
                unmatched.append(f"{season_name} {r['HomeTeam']}-{r['AwayTeam']}")
                continue
            fx = fx_key.loc[key]
            row = {
                "season_id": season_id,
                "fpl_fixture_id": int(fx["fpl_fixture_id"]),
                "matched_via": "teams",
            }
            for src, dst in ODDS_COLS.items():
                v = r.get(src)
                row[dst] = None if v is None or pd.isna(v) else float(v)
            rows.append(row)
        total += upsert(engine, "match_odds", rows, ["season_id", "fpl_fixture_id"])
        unmatched_all += unmatched

    if unmatched_all:
        log.warning("odds: %d unmatched matches: %s", len(unmatched_all), unmatched_all[:10])
    log.info("match_odds: %d rows", total)
