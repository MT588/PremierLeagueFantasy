"""CLI orchestrator: python -m pipeline.run_pipeline --historical | --live | --all"""

import argparse
import logging

from sqlalchemy import text

from app.db import engine

TABLES = [
    "seasons", "teams", "team_seasons", "players",
    "player_seasons", "fixtures", "player_gameweeks", "predictions",
]


def print_counts() -> None:
    with engine.connect() as conn:
        print("--- table row counts ---")
        for t in TABLES:
            n = conn.execute(text(f"select count(*) from {t}")).scalar()
            print(f"{t:20s} {n:>10}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical", action="store_true", help="ingest vaastav CSV seasons")
    parser.add_argument("--live", action="store_true", help="sync current season from FPL API")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--seasons", nargs="*", help="subset of seasons, e.g. 2024-25")
    args = parser.parse_args()

    if args.historical or args.all:
        from pipeline.ingest_vaastav import ingest_all

        ingest_all(engine, args.seasons)
    if args.live or args.all:
        from pipeline.ingest_live import sync_live

        sync_live(engine)
    print_counts()


if __name__ == "__main__":
    main()
