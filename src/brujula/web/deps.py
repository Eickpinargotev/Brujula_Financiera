"""Dependencias FastAPI compartidas por las rutas web."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.engine import get_sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Sesión async de BD por request (el commit lo hace la ruta que escribe)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
