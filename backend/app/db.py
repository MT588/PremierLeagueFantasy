from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)

_metadata = MetaData()
_table_cache: dict[str, Table] = {}


def get_table(name: str) -> Table:
    """Reflect a table from the live database (cached)."""
    if name not in _table_cache:
        _table_cache[name] = Table(name, _metadata, autoload_with=engine)
    return _table_cache[name]
