import os

from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

if os.environ.get("VERCEL"):
    # Serverless: connections can't be pooled across invocations, and Supabase's
    # transaction pooler rejects server-side prepared statements.
    engine = create_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
    )
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False)

_metadata = MetaData()
_table_cache: dict[str, Table] = {}


def get_table(name: str) -> Table:
    """Reflect a table from the live database (cached)."""
    if name not in _table_cache:
        _table_cache[name] = Table(name, _metadata, autoload_with=engine)
    return _table_cache[name]
