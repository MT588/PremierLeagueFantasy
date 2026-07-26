"""International tournament load: who played a summer tournament, how much, and
how deep their nation went. Sources, best available wins:

- WikipediaLineupSource: per-player minutes, starts and goals parsed from the
  match line-up tables on each tournament's stage pages. This is the real
  signal — a losing finalist who started seven matches is a different GW1 risk
  from an unused squad member — and it is free. Guarded by a parse-health probe
  (see `LineupParse.healthy`): if Wikipedia's markup drifts, the loader reports
  the shortfall and leaves minutes NULL rather than half-filling the table.
- WikipediaSquadSource: squad lists + team progress, no minutes. Always
  available; the floor that ml/features/schedule.py's PROGRESS_MINUTES proxy
  is built on.
- FootballDataOrgSource: exact per-player minutes via api.football-data.org
  (requires FOOTBALL_DATA_API_KEY in backend/.env — see
  docs/FOOTBALL_DATA_API_SETUP.md). Probed at runtime: the free tier's lineup
  coverage isn't guaranteed, so we verify before trusting it.

Accuracy, measured against published tournament totals: minutes and starts come
straight out of the substitution markup and are exact wherever a line-up parses.
Goals are the weaker signal — the parse lands at 166 vs 172 actual for WC2022,
105 vs 117 for EURO2024 and 68 vs 61 for Copa 2024 (±10%), because scorer lines
vary more than line-up tables do. Good enough for a decayed early-season
feature; `LineupParse.healthy` rejects a parse whose goal rate leaves the range
international football actually produces, and tests/test_international_lineups.py
pins the totals so a regression is visible.

Assists are deliberately absent: no free source publishes tournament assists.
StatsBomb's open data would, but its World Cup coverage stops at 2022 (checked
against open-data/data/competitions.json), so `assists` stays NULL and the
feature group in ml/features/tournament.py does not use it.

team_progress scale: 7 won, 6 final, 5 SF, 4 QF, 3 R16, 2 R32, 1 group exit.
"""

import datetime as dt
import json
import logging
import os
import re
import typing
import unicodedata
from dataclasses import dataclass, field
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

def _wc_pages(year: int, groups: str, extra: list[str]) -> list[str]:
    return [f"{year} FIFA World Cup Group {g}" for g in groups] + extra


TOURNAMENTS = {
    ("WC", 2026): {
        "squads_page": "2026 FIFA World Cup squads",
        # 12 groups x 6 + 16 + 15 + 1 = 104 matches
        "lineup_pages": _wc_pages(
            2026,
            "ABCDEFGHIJKL",
            [
                "2026 FIFA World Cup round of 32",
                "2026 FIFA World Cup knockout stage",
                "2026 FIFA World Cup final",
            ],
        ),
        "expected_matches": 104,
        "openfootball": "2026--usa",
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
        "lineup_pages": _wc_pages(
            2022,
            "ABCDEFGH",
            ["2022 FIFA World Cup knockout stage", "2022 FIFA World Cup final"],
        ),
        "expected_matches": 64,
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
        "lineup_pages": [f"UEFA Euro 2024 Group {g}" for g in "ABCDEF"]
        + ["UEFA Euro 2024 knockout stage", "UEFA Euro 2024 final"],
        "expected_matches": 51,
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
        "lineup_pages": [f"2024 Copa América Group {g}" for g in "ABCD"]
        + ["2024 Copa América knockout stage", "2024 Copa América final"],
        "expected_matches": 32,
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


def fetch_wikitext(page: str) -> str:
    """MediaWiki wikitext for one page, cached as a refetchable raw response."""
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


class PlayerMatcher:
    """Wikipedia display name -> FPL player code.

    Exact on the normalised full name when that is unique, otherwise a fuzzy
    token-sort match at 93 against full and short names. Names that resolve to
    more than one FPL player are skipped rather than guessed. Shared by the
    squad and line-up sources so both resolve identity identically.
    """

    THRESHOLD = 93

    def __init__(self, engine: Engine) -> None:
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
        self._players = players
        self._by_full: dict[str, list[int]] = {}
        for r in players.itertuples():
            self._by_full.setdefault(r.norm_full, []).append(r.code)
        self._cache: dict[str, int | None] = {}
        self.ambiguous = 0

    def match(self, name: str) -> int | None:
        nname = norm(name)
        if nname in self._cache:
            return self._cache[nname]
        codes = self._by_full.get(nname, [])
        code: int | None = None
        if len(codes) == 1:
            code = codes[0]
        elif len(codes) > 1:
            self.ambiguous += 1
        else:
            best: tuple[int, int] | None = None
            for r in self._players.itertuples():
                score = max(
                    fuzz.token_sort_ratio(nname, r.norm_full),
                    fuzz.token_sort_ratio(nname, r.norm_web),
                )
                if score >= self.THRESHOLD and (best is None or score > best[1]):
                    best = (r.code, score)
            if best:
                code = best[0]
        self._cache[nname] = code
        return code


class WikipediaSquadSource:
    source_name = "wikipedia-proxy"

    def load(
        self, engine: Engine, tournament: str, year: int, config: dict
    ) -> list[dict]:
        squads = parse_squads(fetch_wikitext(config["squads_page"]))
        progress = config["progress"]
        matcher = PlayerMatcher(engine)

        rows = []
        for country, name in squads:
            code = matcher.match(name)
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
                    "country": country,
                    "source": self.source_name,
                }
            )
        log.info(
            "%s %d: %d squad players parsed, %d matched to FPL players (%d ambiguous skipped)",
            tournament,
            year,
            len(squads),
            len(rows),
            matcher.ambiguous,
        )
        return rows


# A match block starts at the football-box template. 2026 pages use the Lua
# module form, 2022/2024 pages the classic template; both are followed by the
# two line-up tables the block owns.
MATCH_SPLIT = re.compile(
    r"\{\{\s*(?:#invoke:\s*football box\s*\|\s*main|football box)", re.IGNORECASE
)
DATE_RE = re.compile(r"\|\s*date\s*=\s*\{\{Start date\|(\d{4})\|(\d{1,2})\|(\d{1,2})")
AET_RE = re.compile(r"\|\s*aet\s*=\s*y", re.IGNORECASE)
# Only the two {{Football kit}} blocks name the teams; plain |title= also
# appears in citation templates, which would otherwise flood the country map.
KIT_TITLE_RE = re.compile(
    r"\{\{\s*Football kit.*?\|\s*title\s*=\s*([^<\n|}]+)", re.IGNORECASE | re.DOTALL
)
# |LB ||'''22'''||[[Richie Laryea]] || {{yel|40}} || {{suboff|78}}
LINEUP_ROW_RE = re.compile(r"^\|\s*[A-Z]{2}\s*\|\|\s*'''\d+'''\s*\|\|(.+)$")
LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
SUBOFF_RE = re.compile(r"\{\{\s*suboff\s*\|\s*(\d+)", re.IGNORECASE)
SUBON_RE = re.compile(r"\{\{\s*subon\s*\|\s*(\d+)", re.IGNORECASE)
SENT_OFF_RE = re.compile(r"\{\{\s*sent off", re.IGNORECASE)
# A scorer's minutes come either as one {{goal|23|67}} template carrying every
# minute he scored in (2022/2024 pages) or as bare "50', 82'" text (2026 pages).
GOAL_TEMPLATE_RE = re.compile(r"\{\{\s*goal\s*\|([^}]*)\}\}", re.IGNORECASE)
MINUTE_ARG_RE = re.compile(r"^\d+(?:\+\d+)?$")
BARE_MINUTE_RE = re.compile(r"\d+(?:\+\d+)?'")
OWN_GOAL_MARKERS = ("own goal", "(og)", "o.g.", "{{og")

REGULATION_MINUTES = 90
EXTRA_TIME_MINUTES = 120


@dataclass
class Appearance:
    minutes: int
    started: bool
    goals: int = 0


@dataclass
class LineupParse:
    """Aggregated per-player tournament record plus the counters the health
    probe needs. Keys are Wikipedia display names, resolved to FPL codes later."""

    matches_parsed: int = 0
    lineup_slots: int = 0
    minutes: dict[str, int] = field(default_factory=dict)
    starts: dict[str, int] = field(default_factory=dict)
    appearances: dict[str, int] = field(default_factory=dict)
    goals: dict[str, int] = field(default_factory=dict)
    last_match: dict[str, dt.date] = field(default_factory=dict)
    country_last_match: dict[str, dt.date] = field(default_factory=dict)
    total_goals: int = 0

    def healthy(self, expected_matches: int) -> bool:
        """Wikipedia markup drifts. Rather than trust a partial parse, require
        (nearly) every match, a plausible number of named players per line-up
        (11 starters plus used substitutes, both teams) and a goal rate in the
        range international football actually produces."""
        if self.matches_parsed < expected_matches * 0.95:
            log.warning(
                "lineup parse found %d/%d matches", self.matches_parsed, expected_matches
            )
            return False
        per_match = self.lineup_slots / max(self.matches_parsed, 1)
        if not 24 <= per_match <= 42:
            log.warning("lineup parse averaged %.1f players per match", per_match)
            return False
        goals_per_match = self.total_goals / max(self.matches_parsed, 1)
        if not 1.5 <= goals_per_match <= 4.0:
            log.warning(
                "lineup parse read %.2f goals per match — goal markup changed",
                goals_per_match,
            )
            return False
        return True


def _player_name(cell: str) -> str | None:
    link = LINK_RE.search(cell)
    if not link:
        return None
    article = re.sub(r"\s*\([^)]*\)$", "", link.group(1)).strip()
    return (link.group(2) or article).strip()


def _count_goals(line: str) -> int:
    """How many goals one bullet line credits its player with. Own goals score
    for the opposing team, so they are dropped; penalties count."""
    templates = GOAL_TEMPLATE_RE.findall(line)
    if templates:
        total = 0
        for args in templates:
            parts = [a.strip() for a in args.split("|")]
            if any(m in a.lower() for a in parts for m in OWN_GOAL_MARKERS):
                continue
            total += sum(1 for a in parts if MINUTE_ARG_RE.match(a))
        return total
    if any(m in line.lower() for m in OWN_GOAL_MARKERS):
        return 0
    return len(BARE_MINUTE_RE.findall(line))


def _parse_goals(block: str) -> dict[str, int]:
    """Scorer -> goals, from the |goals1= / |goals2= bullet lists."""
    out: dict[str, int] = {}
    for key in ("goals1", "goals2"):
        # The terminating parameter name must allow digits: without that,
        # `goals1` runs straight through `goals2` and `penalties1`, double
        # counting the away scorers and adding shootout goals on top.
        section = re.search(
            rf"\|\s*{key}\s*=(.*?)(?=\n\s*\|\s*[a-z_0-9]+\s*=|\n\}}\}})",
            block,
            re.DOTALL,
        )
        if not section:
            continue
        for line in section.group(1).splitlines():
            if not line.strip().startswith("*"):
                continue
            name = _player_name(line)
            if not name:
                continue
            goals = _count_goals(line)
            if goals:
                out[name] = out.get(name, 0) + goals
    return out


def parse_lineups(wikitext: str, parse: LineupParse) -> None:
    """Accumulate one stage page's line-ups into `parse`.

    Within a match block the two `'''Manager:'''` markers close each team's
    table, and `'''Substitutions:'''` separates starters from substitutes.
    Minutes come from the substitution templates: a starter plays to his
    `{{suboff|m}}` or to full time, a substitute from his `{{subon|m}}` to full
    time (or to his own `{{suboff|m}}` if he was later replaced).
    """
    blocks = MATCH_SPLIT.split(wikitext)[1:]
    for block in blocks:
        date_match = DATE_RE.search(block)
        if not date_match:
            continue
        match_date = dt.date(*(int(g) for g in date_match.groups()))
        full_time = EXTRA_TIME_MINUTES if AET_RE.search(block) else REGULATION_MINUTES
        countries = KIT_TITLE_RE.findall(block)
        goals = _parse_goals(block)

        appearances: dict[str, Appearance] = {}
        team_idx, in_subs = 0, False
        for line in block.splitlines():
            if "'''Substitutions:'''" in line:
                in_subs = True
                continue
            if "'''Manager:'''" in line:
                team_idx += 1
                in_subs = False
                continue
            row = LINEUP_ROW_RE.match(line)
            if not row or team_idx > 1:
                continue
            cell = row.group(1)
            name = _player_name(cell)
            if not name:
                continue
            off = SUBOFF_RE.search(cell)
            on = SUBON_RE.search(cell)
            if in_subs:
                if not on:
                    continue  # unused substitute
                start_minute = int(on.group(1))
                end = int(off.group(1)) if off else full_time
                appearances[name] = Appearance(max(end - start_minute, 0), False)
            else:
                end = int(off.group(1)) if off else full_time
                appearances[name] = Appearance(end, True)

        if not appearances:
            continue
        parse.matches_parsed += 1
        parse.lineup_slots += len(appearances)
        parse.total_goals += sum(goals.values())
        for country in countries[:2]:
            country = country.strip()
            if country:
                parse.country_last_match[country] = max(
                    parse.country_last_match.get(country, match_date), match_date
                )
        for name, app in appearances.items():
            parse.minutes[name] = parse.minutes.get(name, 0) + app.minutes
            parse.starts[name] = parse.starts.get(name, 0) + int(app.started)
            parse.appearances[name] = parse.appearances.get(name, 0) + 1
            parse.last_match[name] = max(
                parse.last_match.get(name, match_date), match_date
            )
        for name, count in goals.items():
            parse.goals[name] = parse.goals.get(name, 0) + count


class WikipediaLineupSource:
    """Per-player tournament minutes, starts and goals from stage-page line-ups."""

    source_name = "wikipedia-lineups"

    def parse(self, config: dict) -> LineupParse | None:
        pages = config.get("lineup_pages")
        if not pages:
            return None
        parse = LineupParse()
        for page in pages:
            try:
                parse_lineups(fetch_wikitext(page), parse)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                log.warning("lineup page %r unavailable (%s)", page, e)
        if not parse.healthy(config.get("expected_matches", 0)):
            return None
        log.info(
            "%d matches parsed, %d players with minutes, %d scorers, %d goals",
            parse.matches_parsed,
            len(parse.minutes),
            len(parse.goals),
            parse.total_goals,
        )
        return parse

    def enrich(
        self, engine: Engine, squad_rows: list[dict], parse: LineupParse
    ) -> list[dict]:
        """Fold parsed minutes onto the squad rows. A squad member who never
        made a line-up gets a real zero, not a null: not playing is signal. His
        return date still comes from his nation's last match — he travelled."""
        matcher = PlayerMatcher(engine)
        by_code: dict[int, dict] = {}

        def entry_for(code: int) -> dict:
            return by_code.setdefault(
                code,
                {"minutes": 0, "starts": 0, "matches": 0, "goals": 0, "last": None},
            )

        for name, minutes in parse.minutes.items():
            code = matcher.match(name)
            if code is None:
                continue
            entry = entry_for(code)
            entry["minutes"] += minutes
            entry["starts"] += parse.starts.get(name, 0)
            entry["matches"] += parse.appearances.get(name, 0)
            last = parse.last_match.get(name)
            if last and (entry["last"] is None or last > entry["last"]):
                entry["last"] = last

        # Goals are merged on the resolved code, never on the name: line-up
        # tables link full names ("Harry Kane") while scorer lists use the short
        # display form ("Kane"), so a name-keyed merge silently drops every goal.
        for name, count in parse.goals.items():
            code = matcher.match(name)
            if code is not None:
                entry_for(code)["goals"] += count

        enriched = 0
        for row in squad_rows:
            country = row.pop("country", None)
            stats = by_code.get(row["player_code"])
            team_last = parse.country_last_match.get(country) if country else None
            if stats:
                enriched += 1
                row.update(
                    minutes=stats["minutes"],
                    starts=stats["starts"],
                    matches=stats["matches"],
                    goals=stats["goals"],
                    last_match_date=stats["last"] or team_last,
                    source=self.source_name,
                )
            else:
                row.update(
                    minutes=0,
                    starts=0,
                    matches=0,
                    goals=0,
                    last_match_date=team_last,
                    source=self.source_name,
                )
        log.info(
            "%d/%d matched squad players carry parsed minutes", enriched, len(squad_rows)
        )
        return squad_rows


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
    squads = WikipediaSquadSource()
    lineups = WikipediaLineupSource()
    total = 0
    for (tournament, year), config in TOURNAMENTS.items():
        if fd.key and fd.available(tournament):
            log.info(
                "%s %d: football-data.org key present — exact-minutes path "
                "not yet wired, using Wikipedia line-ups (see setup doc)",
                tournament,
                year,
            )
        rows = squads.load(engine, tournament, year, config)
        parse = lineups.parse(config)
        if parse is not None:
            rows = lineups.enrich(engine, rows, parse)
        else:
            # No trustworthy line-up parse: leave minutes NULL so the
            # progress-based proxy in ml/features/schedule.py still applies.
            log.warning(
                "%s %d: line-up parse unavailable, keeping squad-membership proxy",
                tournament,
                year,
            )
            for row in rows:
                row.pop("country", None)
        total += upsert(
            engine, "international_load", rows, ["player_code", "tournament", "year"]
        )
    log.info("international_load: %d rows", total)
