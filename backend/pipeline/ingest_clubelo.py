"""Ingest ClubElo rating history for every PL club in the database.

http://api.clubelo.com/{ClubName} returns the club's full Elo history as CSV
(Rank,Club,Country,Level,Elo,From,To validity ranges). Plain HTTP only.
One request per club (~30), cached to data/raw/clubelo/.
"""

import io
import logging
import time
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import Engine, text

from pipeline.ingest_vaastav import records
from pipeline.team_names import clubelo_name
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "clubelo"
CUTOFF = "2021-06-01"

# ClubElo URL slugs that aren't simply the display name with spaces stripped
SLUG_EXCEPTIONS: dict[str, str] = {}


def fetch_club_history(name: str) -> pd.DataFrame:
    """Fetch (or read cached) Elo history. The API occasionally 503s and
    returns header-only CSVs transiently, so retry and never cache emptiness."""
    slug = SLUG_EXCEPTIONS.get(name) or name.replace(" ", "").replace("'", "")
    cache = CACHE_DIR / f"{slug}.csv"
    if cache.exists():
        df = pd.read_csv(cache)
        if not df.empty:
            return df
        cache.unlink()  # stale empty cache from a transient failure

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            resp = httpx.get(f"http://api.clubelo.com/{slug}", timeout=60)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            if df.empty:
                raise RuntimeError(f"empty ClubElo response for {slug}")
            cache.write_text(resp.text)
            time.sleep(0.5)
            return df
        except Exception as e:  # noqa: BLE001 - retry any fetch/parse failure
            last_error = e
            time.sleep(2**attempt)
    raise RuntimeError(f"ClubElo fetch failed for {slug}: {last_error}")


def ingest_clubelo(engine: Engine) -> None:
    with engine.connect() as conn:
        team_codes = sorted(
            conn.execute(text("select distinct team_code from team_seasons")).scalars()
        )

    total = 0
    for code in team_codes:
        name = clubelo_name(code)
        df = fetch_club_history(name)
        if df.empty or "Elo" not in df.columns:
            raise RuntimeError(f"ClubElo returned no usable data for {name!r}")
        df = df[df["To"] >= CUTOFF]
        out = pd.DataFrame(
            {
                "team_code": code,
                "elo": df["Elo"],
                "valid_from": pd.to_datetime(df["From"]).dt.date,
                "valid_to": pd.to_datetime(df["To"]).dt.date,
            }
        )
        total += upsert(engine, "club_elo", records(out), ["team_code", "valid_from"])
    log.info("club_elo: %d rows for %d clubs", total, len(team_codes))
