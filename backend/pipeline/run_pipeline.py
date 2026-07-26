"""CLI orchestrator: python -m pipeline.run_pipeline [--init] --historical | --live | --all"""

import argparse
import logging
from pathlib import Path

from sqlalchemy import text

from app.db import engine

MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations"
)

TABLES = [
    "seasons",
    "teams",
    "team_seasons",
    "players",
    "player_seasons",
    "fixtures",
    "player_gameweeks",
    "predictions",
    "club_elo",
    "match_odds",
    "understat_players",
    "understat_matches",
    "manager_stints",
    "international_load",
    "european_competitions",
]


def apply_migrations() -> None:
    """Apply supabase/migrations/*.sql in order. All statements are idempotent
    (create table if not exists / enable RLS), so re-running is safe."""
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        print(f"applying {path.name}")
        with engine.begin() as conn:
            conn.exec_driver_sql(path.read_text())


def print_counts() -> None:
    with engine.connect() as conn:
        print("--- table row counts ---")
        for t in TABLES:
            n = conn.execute(text(f"select count(*) from {t}")).scalar()
            print(f"{t:20s} {n:>10}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--init", action="store_true", help="apply schema migrations first"
    )
    parser.add_argument(
        "--historical", action="store_true", help="ingest vaastav CSV seasons"
    )
    parser.add_argument(
        "--live", action="store_true", help="sync current season from FPL API"
    )
    parser.add_argument(
        "--curated", action="store_true", help="manager stints, euro flags, set pieces"
    )
    parser.add_argument(
        "--clubelo", action="store_true", help="ClubElo ratings history"
    )
    parser.add_argument(
        "--odds", action="store_true", help="football-data.co.uk match odds"
    )
    parser.add_argument(
        "--understat", action="store_true", help="Understat xG per match"
    )
    parser.add_argument(
        "--international", action="store_true", help="WC/EURO tournament load"
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--seasons", nargs="*", help="subset of seasons, e.g. 2024-25")
    args = parser.parse_args()

    if args.init:
        apply_migrations()
    if args.historical or args.all:
        from pipeline.ingest_vaastav import ingest_all

        ingest_all(engine, args.seasons)
    if args.live or args.all:
        from pipeline.ingest_live import sync_live

        sync_live(engine)
    if args.curated or args.all:
        from pipeline.load_curated import load_curated

        load_curated(engine)
    if args.clubelo or args.all:
        from pipeline.ingest_clubelo import ingest_clubelo

        ingest_clubelo(engine)
    if args.odds or args.all:
        from pipeline.ingest_odds import ingest_odds

        ingest_odds(engine)
    if args.understat or args.all:
        from pipeline.ingest_understat import ingest_understat

        ingest_understat(engine)
    if args.international or args.all:
        from pipeline.ingest_international import ingest_international

        ingest_international(engine)
    print_counts()


if __name__ == "__main__":
    main()
