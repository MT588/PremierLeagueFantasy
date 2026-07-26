"""Shared context data loaded once per feature build."""

import io
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import Engine, text

log = logging.getLogger(__name__)

CLUBELO_CACHE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "clubelo"
)

UNDERSTAT_SQL = """
select up.player_code, um.match_date, um.league, um.season, um.minutes,
       um.shots, um.key_passes, um.xg, um.xa, um.npxg
from understat_matches um
join understat_players up on up.understat_id = um.understat_id
where up.player_code is not null
"""

LEAGUE_COUNTRY = {
    "EPL": "ENG",
    "La_liga": "ESP",
    "Bundesliga": "GER",
    "Serie_A": "ITA",
    "Ligue_1": "FRA",
    "RFPL": "RUS",
}


@dataclass
class FeatureContext:
    club_elo: pd.DataFrame  # team_code, valid_from(date as ts), elo
    manager_stints: pd.DataFrame  # team_code, start_date(ts)
    euro: dict[tuple[int, int], int]  # (season_id, team_code) -> 0/1/2
    intl: pd.DataFrame  # per player-tournament: minutes/starts/goals/progress/last match
    setpiece: pd.DataFrame  # season_id, player_code, pen/corner/fk orders
    team_fixtures: pd.DataFrame  # team_code, kickoff_time, goals_for, goals_against
    understat: pd.DataFrame  # per player per match
    league_coefs: dict[tuple[str, int], float]


def _league_coefs() -> dict[tuple[str, int], float]:
    """Elo-scale league strength coefficients per (understat league, season
    start year), from ClubElo daily snapshots (July 1) of each year."""
    coefs: dict[tuple[str, int], float] = {}
    for year in range(2019, 2027):
        cache = CLUBELO_CACHE / f"daily_{year}-07-01.csv"
        if cache.exists():
            df = pd.read_csv(cache)
        else:
            try:
                resp = httpx.get(f"http://api.clubelo.com/{year}-07-01", timeout=60)
                resp.raise_for_status()
                CLUBELO_CACHE.mkdir(parents=True, exist_ok=True)
                cache.write_text(resp.text)
                df = pd.read_csv(io.StringIO(resp.text))
            except httpx.HTTPError as e:
                log.warning("clubelo daily %d unavailable (%s)", year, e)
                continue
        top = df[df["Level"] == 1]
        means = top.groupby("Country")["Elo"].mean()
        epl = means.get("ENG")
        if epl is None:
            continue
        for league, country in LEAGUE_COUNTRY.items():
            if country in means:
                coefs[(league, year)] = float(
                    min(1.0, max(0.5, 10 ** ((means[country] - epl) / 400)))
                )
    return coefs


def load_context(engine: Engine) -> FeatureContext:
    with engine.connect() as conn:
        club_elo = pd.read_sql(
            text("select team_code, valid_from, elo from club_elo"), conn
        )
        stints = pd.read_sql(
            text("select team_code, start_date from manager_stints"), conn
        )
        euro_rows = conn.execute(
            text("select season_id, team_code, competition from european_competitions")
        ).all()
        intl = pd.read_sql(
            text(
                "select player_code, tournament, year, minutes, matches, starts, "
                "goals, team_progress, last_match_date from international_load"
            ),
            conn,
        )
        setpiece = pd.read_sql(
            text(
                "select season_id, player_code, penalties_order, corners_order, "
                "freekicks_order from player_seasons"
            ),
            conn,
        )
        fixtures = pd.read_sql(
            text(
                "select kickoff_time, home_team_code, away_team_code, "
                "home_score, away_score, finished from fixtures "
                "where kickoff_time is not null"
            ),
            conn,
        )
        understat = pd.read_sql(text(UNDERSTAT_SQL), conn)

    club_elo["valid_from"] = pd.to_datetime(club_elo["valid_from"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    club_elo = club_elo.sort_values("valid_from")

    stints["start_date"] = pd.to_datetime(stints["start_date"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    stints = stints.sort_values("start_date")

    euro = {
        (r.season_id, r.team_code): {"UECL": 1, "UEL": 1, "UCL": 2}[r.competition]
        for r in euro_rows
    }

    fixtures["kickoff_time"] = pd.to_datetime(
        fixtures["kickoff_time"], utc=True
    ).astype("datetime64[ns, UTC]")
    home = fixtures.rename(
        columns={
            "home_team_code": "team_code",
            "home_score": "goals_for",
            "away_score": "goals_against",
        }
    )[["team_code", "kickoff_time", "goals_for", "goals_against", "finished"]]
    away = fixtures.rename(
        columns={
            "away_team_code": "team_code",
            "away_score": "goals_for",
            "home_score": "goals_against",
        }
    )[["team_code", "kickoff_time", "goals_for", "goals_against", "finished"]]
    team_fixtures = (
        pd.concat([home, away], ignore_index=True)
        .sort_values("kickoff_time")
        .reset_index(drop=True)
    )

    understat["match_date"] = pd.to_datetime(understat["match_date"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    understat = understat.sort_values("match_date")

    return FeatureContext(
        club_elo=club_elo,
        manager_stints=stints,
        euro=euro,
        intl=intl,
        setpiece=setpiece,
        team_fixtures=team_fixtures,
        understat=understat,
        league_coefs=_league_coefs(),
    )
