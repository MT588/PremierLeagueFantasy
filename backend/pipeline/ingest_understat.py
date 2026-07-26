"""Ingest Understat per-match xG data for all FPL players.

Understat now serves data from JSON endpoints rather than embedded page
variables (discovered by reading the site's own JS):
  POST /main/getPlayersStats/  {league, season}  -> season player list
  GET  /getPlayerData/{id}                        -> full career payload

One getPlayerData request per matched player covers their entire cross-league
career, so transfers cost no extra requests. All responses are cached to
data/raw/understat/; uncached requests are spaced ~1.1s apart.
"""

import json
import logging
import time
from pathlib import Path

import httpx
from sqlalchemy import Engine, text

from pipeline.match_players import match_epl_players, match_foreign_players
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "understat"
BASE = "https://understat.com"
HEADERS = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}

LEAGUES = ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1", "RFPL"]
MAP_SEASONS = list(range(2019, 2026))       # team->league map + foreign pools
EPL_MATCH_SEASONS = list(range(2021, 2026))  # seasons we match identities for
MIN_MATCH_SEASON = 2018                      # oldest per-match rows we store

_last_request = 0.0


def _throttled_request(method: str, url: str, **kwargs) -> httpx.Response:
    global _last_request
    wait = 1.1 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        try:
            resp = httpx.request(method, url, headers=HEADERS, timeout=60, **kwargs)
            _last_request = time.monotonic()
            resp.raise_for_status()
            return resp
        except httpx.HTTPError:
            if attempt == 3:
                raise
            time.sleep(3 * 2**attempt)
    raise AssertionError("unreachable")


def fetch_players_stats(league: str, season: int) -> list[dict]:
    cache = CACHE_DIR / f"league_{league}_{season}.json"
    if cache.exists():
        return json.loads(cache.read_text())["players"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    resp = _throttled_request(
        "POST", f"{BASE}/main/getPlayersStats/", data={"league": league, "season": season}
    )
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"getPlayersStats failed for {league} {season}")
    cache.write_text(resp.text)
    return data["players"]


def fetch_player_data(understat_id: int) -> dict:
    cache = CACHE_DIR / f"player_{understat_id}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    resp = _throttled_request("GET", f"{BASE}/getPlayerData/{understat_id}")
    data = resp.json()
    cache.write_text(resp.text)
    return data


def build_team_league_map() -> dict[str, str]:
    team_league: dict[str, str] = {}
    for league in LEAGUES:
        for season in MAP_SEASONS:
            for p in fetch_players_stats(league, season):
                for title in p["team_title"].split(","):
                    team_league[title.strip()] = league
    return team_league


def matches_to_rows(understat_id: int, payload: dict, team_league: dict[str, str]) -> list[dict]:
    rows: dict[int, dict] = {}
    for m in payload.get("matches", []):
        season = int(m["season"])
        if season < MIN_MATCH_SEASON:
            continue
        league = team_league.get(m["h_team"]) or team_league.get(m["a_team"]) or "unknown"
        rows[int(m["id"])] = (  # dict keyed by match id dedups repeated entries
            {
                "understat_id": understat_id,
                "understat_match_id": int(m["id"]),
                "match_date": m["date"],
                "league": league,
                "season": season,
                "home_team": m["h_team"],
                "away_team": m["a_team"],
                "is_home": None,
                "minutes": int(m["time"]),
                "goals": int(m["goals"]),
                "assists": int(m["assists"]),
                "shots": int(m["shots"]),
                "key_passes": int(m["key_passes"]),
                "xg": float(m["xG"]),
                "xa": float(m["xA"]),
                "npxg": float(m["npxG"]),
                "npg": int(m["npg"]),
                "position": m.get("position"),
            }
        )
    return list(rows.values())


def ingest_understat(engine: Engine) -> None:
    team_league = build_team_league_map()
    log.info("understat: team->league map covers %d clubs", len(team_league))

    epl_pools = {s: fetch_players_stats("EPL", s) for s in EPL_MATCH_SEASONS}
    identities = match_epl_players(engine, epl_pools)

    foreign_pools = {
        (lg, s): fetch_players_stats(lg, s)
        for lg in LEAGUES
        if lg != "EPL"
        for s in (2024, 2025)
    }
    identities += match_foreign_players(engine, foreign_pools, identities)

    n = upsert(engine, "understat_players", identities, ["understat_id"])
    log.info("understat_players: %d rows", n)

    matched = [r for r in identities if r["player_code"] is not None]
    total_rows, done = 0, 0
    for row in matched:
        payload = fetch_player_data(row["understat_id"])
        rows = matches_to_rows(row["understat_id"], payload, team_league)
        total_rows += upsert(
            engine, "understat_matches", rows, ["understat_id", "understat_match_id"]
        )
        done += 1
        if done % 100 == 0:
            log.info("understat: %d/%d players fetched (%d match rows)", done, len(matched), total_rows)
    log.info("understat_matches: %d rows for %d players", total_rows, len(matched))
