"""Thin client for the official FPL API (no auth required)."""

import asyncio
import json
import logging
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "PLFantasy/1.0"}

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "fpl"


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=15))
def get_json(path: str) -> dict | list:
    resp = httpx.get(f"{settings.fpl_api_base}/{path}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def bootstrap_static() -> dict:
    return get_json("bootstrap-static/")


def game_config(season: str, refresh: bool = False) -> dict:
    """The official scoring/rules payload for the current season, cached as a
    refetchable raw response. ml/scoring.py reads this rather than hard-coding
    the points matrix, so a mid-season rule change is picked up by a `--live`
    run instead of being silently mispriced.

    Only the current season is served by the API; historical rule sets live in
    ml/scoring.SEASON_OVERRIDES.
    """
    cache = CACHE_DIR / f"game_config_{season}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    config = bootstrap_static()["game_config"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(config, indent=1), encoding="utf-8")
    log.info("cached FPL game_config for %s", season)
    return config


def fixtures() -> list:
    return get_json("fixtures/")


async def element_summaries(
    element_ids: list[int], concurrency: int = 8
) -> dict[int, dict]:
    """Fetch element-summary for many players with bounded concurrency."""
    sem = asyncio.Semaphore(concurrency)
    results: dict[int, dict] = {}

    async with httpx.AsyncClient(
        base_url=settings.fpl_api_base, headers=HEADERS, timeout=30
    ) as client:

        async def fetch(eid: int) -> None:
            async with sem:
                for attempt in range(4):
                    try:
                        resp = await client.get(f"/element-summary/{eid}/")
                        resp.raise_for_status()
                        results[eid] = resp.json()
                        return
                    except (httpx.HTTPError, httpx.HTTPStatusError):
                        if attempt == 3:
                            raise
                        await asyncio.sleep(2**attempt)

        await asyncio.gather(*(fetch(eid) for eid in element_ids))
    return results
