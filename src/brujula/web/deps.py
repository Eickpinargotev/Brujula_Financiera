"""Dependencias FastAPI compartidas por las rutas web."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from brujula.db.engine import get_sessionmaker
from brujula.db.models import Parameter
from brujula.db.safety import backup_database, database_path

_write_lock = asyncio.Lock()
logger = logging.getLogger(__name__)


async def get_session(request: Request, response: Response) -> AsyncIterator[AsyncSession]:
    """Sesión async de BD por request (el commit lo hace la ruta que escribe)."""
    sessionmaker = get_sessionmaker()
    writing = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    if writing:
        await _write_lock.acquire()
    try:
        async with sessionmaker() as session:
            identity = await session.get(Parameter, "database_identity")
            if identity:
                response.headers["X-Brujula-Database"] = identity.value
                expected = request.headers.get("X-Brujula-Database")
                if expected and expected != identity.value:
                    raise HTTPException(
                        409, "La base de datos cambió. Revisa la conexión antes de guardar."
                    )
            if writing:
                bind = session.bind
                # Las pruebas usan SQLite en memoria; la aplicación usa siempre archivo.
                if (
                    isinstance(bind, AsyncEngine)
                    and bind.url.database not in (None, "", ":memory:")
                ):
                    try:
                        await asyncio.to_thread(
                            backup_database, database_path(str(bind.url)),
                        )
                    except Exception as exc:
                        logger.exception("Escritura bloqueada: no se pudo respaldar la base")
                        raise HTTPException(
                            503, "Falló el respaldo de seguridad. No se aplicaron cambios."
                        ) from exc
            yield session
    finally:
        if writing:
            _write_lock.release()
