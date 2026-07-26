"""Every team code in the database must have external-source name mappings —
a newly promoted club should fail here, not silently lose Elo/odds data."""

from sqlalchemy import text

from app.db import engine
from pipeline.team_names import TEAM_NAMES


def test_all_team_codes_mapped():
    with engine.connect() as conn:
        codes = set(
            conn.execute(text("select distinct team_code from team_seasons")).scalars()
        )
    missing = codes - set(TEAM_NAMES)
    assert not missing, f"team codes without name mappings: {missing}"


def test_mapping_tuples_complete():
    for code, names in TEAM_NAMES.items():
        assert len(names) == 3 and all(n.strip() for n in names), code
