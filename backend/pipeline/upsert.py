import math
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert

from app.db import get_table

CHUNK = 1000


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    """Replace NaN/NaT with None so Postgres gets NULLs."""
    out = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            out[k] = None
        else:
            out[k] = v
    return out


def upsert(engine: Engine, table_name: str, rows: list[dict], conflict_cols: list[str]) -> int:
    """Batched INSERT ... ON CONFLICT DO UPDATE. Returns number of rows sent."""
    if not rows:
        return 0
    table = get_table(table_name)
    rows = [_clean(r) for r in rows]
    update_cols = [c for c in rows[0] if c not in conflict_cols]
    with engine.begin() as conn:
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i : i + CHUNK]
            stmt = insert(table).values(chunk)
            if update_cols:
                stmt = stmt.on_conflict_do_update(
                    index_elements=conflict_cols,
                    set_={c: stmt.excluded[c] for c in update_cols},
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
            conn.execute(stmt)
    return len(rows)
