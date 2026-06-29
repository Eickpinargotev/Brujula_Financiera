"""Engine y sesión async de SQLAlchemy sobre SQLite (aiosqlite)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from brujula.config.settings import Settings, get_settings
from brujula.db.models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Devuelve (creando si hace falta) el engine async global."""
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        _engine = create_async_engine(settings.database_url, future=True)
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
