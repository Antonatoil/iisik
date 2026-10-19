"""Independent connection pools per database; no cross-database joins."""
import os
from functools import lru_cache
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL

DATABASES = frozenset("atlprnx")


@lru_cache(maxsize=7)
def engine(owner: str) -> Engine:
    if owner not in DATABASES:
        raise ValueError("Unknown service database")
    url = URL.create(
        drivername="postgresql+psycopg",
        username=f"svc_{owner}",
        password=os.environ.get("DB_PASSWORD", "service_demo_only"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5434")),
        database=f"tutor_{owner}",
    )
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2)


def rows(owner: str, statement: str, params: dict | None = None) -> list[dict]:
    with engine(owner).connect() as conn:
        return [dict(item) for item in conn.execute(text(statement), params or {}).mappings()]


def one(owner: str, statement: str, params: dict | None = None) -> dict | None:
    records = rows(owner, statement, params)
    return records[0] if records else None
