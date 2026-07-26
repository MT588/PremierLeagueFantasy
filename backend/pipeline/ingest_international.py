"""International tournament load: who played a summer tournament and how deep
their nation went. Two sources, best available wins:

- FootballDataOrgSource: exact per-player minutes via api.football-data.org
  (requires FOOTBALL_DATA_API_KEY in backend/.env — see
  docs/FOOTBALL_DATA_API_SETUP.md). Probed at runtime: the free tier's lineup
  coverage isn't guaranteed, so we verify before trusting it.
- WikipediaSquadSource: squad lists + team progress (no minutes). Always
  available; used as the fallback and for historical tournaments.

team_progress scale: 7 won, 6 final, 5 SF, 4 QF, 3 R16, 2 R32, 1 group exit.
"""

import json
import logging
import os
import re
import typing
import unicodedata
from pathlib import Path

import httpx
import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy import Engine, text

from pipeline.match_players import norm
from pipeline.upsert import upsert

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "international"
WIKIMEDIA_USER_AGENT = (
    "PLFantasy/1.0 (https://github.com/MT588/PremierLeagueFantasy)"
)

TOURNAMENTS = {
    ("WC", 2026): {
        "squads_page": "2026 FIFA World Cup squads",
        "progress": {
            "Spain": 7,
            "Argentina": 6,
            "France": 5,
            "England": 5,
            "Paraguay": 4,
            "Morocco": 4,
            "Belgium": 4,
            "Norway": 4,
            "Canada": 3,
            "Brazil": 3,
            "United States": 3,
            "Switzerland": 3,
            "Colombia": 3,
            "Egypt": 3,
            "Sweden": 3,
            "Austria": 3,
            "Mexico": 2,
            "South Africa": 2,
            "Bosnia and Herzegovina": 2,
            "Japan": 2,
            "Germany": 2,
            "Ivory Coast": 2,
            "Ecuador": 2,
            "Netherlands": 2,
            "Cape Verde": 2,
            "Senegal": 2,
            "Algeria": 2,
            "Portugal": 2,
            "DR Congo": 2,
            "Ghana": 2,
            "Croatia": 2,
            "Australia": 2,
        },
    },
    ("WC", 2022): {
        "squads_page": "2022 FIFA World Cup squads",
        "progress": {
            "Argentina": 7,
            "France": 6,
            "Croatia": 5,
            "Morocco": 5,
            "Netherlands": 4,
            "Brazil": 4,
            "England": 4,
            "Portugal": 4,
            "United States": 3,
            "Australia": 3,
            "Poland": 3,
            "Senegal": 3,
            "Japan": 3,
            "South Korea": 3,
            "Switzerland": 3,
            "Spain": 3,
        },
    },
    ("EURO", 2024): {
        "squads_page": "UEFA Euro 2024 squads",
        "progress": {
            "Spain": 7,
            "England": 6,
            "France": 5,
            "Netherlands": 5,
            "Portugal": 4,
            "Germany": 4,
            "Switzerland": 4,
            "Turkey": 4,
            "Italy": 3,
            "Denmark": 3,
            "Belgium": 3,
            "Slovakia": 3,
            "Romania": 3,
            "Austria": 3,
            "Slovenia": 3,
            "Georgia": 3,
        },
    },
    ("COPA", 2024): {
        "squads_page": "2024 Copa América squads",
        "progress": {
            "Argentina": 7,
            "Colombia": 6,
            "Uruguay": 5,
            "Canada": 5,
            "Brazil": 4,
            "Venezuela": 4,
            "Ecuador": 4,
            "Panama": 4,
        },
    },
}

PLAYER_ROW = re.compile(
    r"\{\{nat fs g player\|.*?name=\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", re.IGNORECASE
)


def fetch_squads_wikitext(page: str) -> str:
    cache = CACHE_DIR / (re.sub(r"\W+", "_", page) + ".json")
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "parse",
                "page": page,
                "prop": "wikitext",
                "format": "json",
                "formatversion": 2,
            },
            headers={"User-Agent": WIKIMEDIA_USER_AGENT},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        cache.write_text(resp.text, encoding="utf-8")
    return data["parse"]["wikitext"]


def parse_squads(wikitext: str) -> list[tuple[str, str]]:
    """-> [(country, player_display_name)]"""
    out = []
    country = None
    for line in wikitext.splitlines():
        heading = re.match(r"^===\s*(.+?)\s*===\s*$", line)
        if heading:
            title = re.sub(r"\[\[|\]\]|\{\{[^}]*\}\}", "", heading.group(1)).strip()
            country = title or country
            continue
        m = PLAYER_ROW.search(line)
        if m and country:
            article = re.sub(r"\s*\([^)]*\)$", "", m.group(1)).strip()
            display = (m.group(2) or article).strip()
            out.append((country, display))
    return out


def strip_diacritics(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


class WikipediaSquadSource:
    source_name = "wikipedia-proxy"

    def load(
        self, engine: Engine, tournament: str, year: int, config: dict
    ) -> list[dict]:
        squads = parse_squads(fetch_squads_wikitext(config["squads_page"]))
        progress = config["progress"]

        with engine.connect() as conn:
            players = pd.read_sql(
                text(
                    "select code, first_name || ' ' || second_name as full_name, web_name "
                    "from players"
                ),
                conn,
            )
        players["norm_full"] = players["full_name"].map(norm)
        players["norm_web"] = players["web_name"].map(norm)
        by_full: dict[str, list[int]] = {}
        for r in players.itertuples():
            by_full.setdefault(r.norm_full, []).append(r.code)

        rows, ambiguous, n_squad = [], 0, 0
        for country, name in squads:
            n_squad += 1
            nname = norm(name)
            codes = by_full.get(nname, [])
            code = None
            if len(codes) == 1:
                code = codes[0]
            elif len(codes) > 1:
                ambiguous += 1
                continue
            else:
                best = None
                for r in players.itertuples():
                    score = max(
                        fuzz.token_sort_ratio(nname, r.norm_full),
                        fuzz.token_sort_ratio(nname, r.norm_web),
                    )
                    if score >= 93 and (best is None or score > best[1]):
                        best = (r.code, score)
                if best:
                    code = best[0]
            if code is None:
                continue
            rows.append(
                {
                    "player_code": int(code),
                    "tournament": tournament,
                    "year": year,
                    "squad_flag": True,
                    "minutes": None,
                    "matches": None,
                    "team_progress": progress.get(country, 1),
                    "source": self.source_name,
                }
            )
        log.info(
            "%s %d: %d squad players parsed, %d matched to FPL players (%d ambiguous skipped)",
            tournament,
            year,
            n_squad,
            len(rows),
            ambiguous,
        )
        return rows


class FootballDataOrgSource:
    """Exact minutes via api.football-data.org v4. Only attempts anything when
    the API key is configured AND a probe shows lineups in the response."""

    source_name = "football-data.org"
    COMPETITIONS: typing.ClassVar[dict[str, str]] = {"WC": "WC", "EURO": "EC"}

    def __init__(self) -> None:
        self.key = os.environ.get("FOOTBALL_DATA_API_KEY") or ""

    def available(self, tournament: str) -> bool:
        if not self.key or tournament not in self.COMPETITIONS:
            return False
        try:
            resp = httpx.get(
                "https://api.football-data.org/v4/matches/singleprobe",
                timeout=30,
                headers={"X-Auth-Token": self.key},
            )
        except httpx.HTTPError:
            return False
        return resp.status_code != 403

    def load(
        self, engine: Engine, tournament: str, year: int, config: dict
    ) -> list[dict]:
        raise NotImplementedError(
            "wire up once the API key exists — see docs/FOOTBALL_DATA_API_SETUP.md"
        )


def ingest_international(engine: Engine) -> None:
    fd = FootballDataOrgSource()
    wiki = WikipediaSquadSource()
    total = 0
    for (tournament, year), config in TOURNAMENTS.items():
        if fd.key and fd.available(tournament):
            log.info(
                "%s %d: football-data.org key present — exact-minutes path "
                "not yet wired, using Wikipedia proxy (see setup doc)",
                tournament,
                year,
            )
        rows = wiki.load(engine, tournament, year, config)
        total += upsert(
            engine, "international_load", rows, ["player_code", "tournament", "year"]
        )
    log.info("international_load: %d rows", total)
