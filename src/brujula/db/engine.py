"""Engine y sesión async de SQLAlchemy sobre SQLite (aiosqlite).

Robustez para un proceso web con accesos concurrentes:
- WAL: lecturas y escrituras no se bloquean entre sí y el archivo tolera cortes de luz.
- busy_timeout: si una escritura coincide con otra, espera en vez de fallar con
  "database is locked".
- pool_pre_ping: valida la conexión antes de usarla (se recupera sola si se cerró).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from brujula.config.settings import Settings, get_settings
from brujula.db.models import Base
from brujula.db.safety import database_path

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _configurar_sqlite(dbapi_conn: Any, _record: Any) -> None:
    """PRAGMAs de resiliencia aplicados a cada conexión nueva."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=FULL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Devuelve (creando si hace falta) el engine async global."""
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        path = database_path(settings.database_url)
        if not path.is_file() and not settings.allow_database_create:
            raise RuntimeError("La base configurada no existe. Revisa el volumen persistente.")
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["timeout"] = 30  # espera del driver ante bloqueos (segundos)
        _engine = create_async_engine(
            settings.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if _engine.dialect.name == "sqlite":
            event.listen(_engine.sync_engine, "connect", _configurar_sqlite)
    return _engine


def get_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Devuelve (creando si hace falta) el sessionmaker async global."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(settings), expire_on_commit=False)
    return _sessionmaker


async def create_all(engine: AsyncEngine) -> None:
    """Crea todas las tablas si no existen (no usamos migraciones para SQLite single-user)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
