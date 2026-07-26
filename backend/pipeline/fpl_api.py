"""Thin client for the official FPL API (no auth required)."""

import asyncio

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

HEADERS = {"User-Agent": "PLFantasy/1.0"}


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=15))
def get_json(path: str) -> dict | list:
    resp = httpx.get(f"{settings.fpl_api_base}/{path}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def bootstrap_static() -> dict:
    return get_json("bootstrap-static/")


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
