"""Entrypoint del dashboard web de Brújula."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from brujula.config.settings import get_settings
from brujula.core.logging import configure_logging
from brujula.db.bootstrap import bootstrap_database
from brujula.db.engine import get_engine
from brujula.web.app import register_web

settings = get_settings()
configure_logging(settings.app_env)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail-fast: en producción no se inicia si faltan variables de entorno requeridas.
    faltan = settings.missing_required()
    if faltan:
        mensaje = "Faltan variables de entorno requeridas: " + ", ".join(faltan)
        if settings.is_production:
            logger.error(mensaje)
            raise RuntimeError(mensaje)
        logger.warning("%s (permitido en desarrollo)", mensaje)

    # Crea las tablas y siembra parámetros/metas/sobres iniciales.
    await bootstrap_database(settings)

    yield


# docs/openapi deshabilitados: no exponer el esquema de la API.
app = FastAPI(
    title="Brújula Financiera",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Monta el dashboard (login + páginas + API de datos) y /static.
register_web(app, settings)


@app.middleware("http")
async def security_and_cache_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Headers de seguridad en todo, y política de caché correcta.

    - Estáticos: caché larga (van versionados con ?v=, así nunca se sirven viejos).
    - Páginas y API: no-store (datos financieros; nada queda cacheado en el navegador).
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/static"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Error genérico hacia afuera; el detalle queda solo en los logs (CLAUDE.md §6)."""
    logger.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno"})


@app.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    """Estado de la app Y de la base de datos (lo usan los healthchecks del contenedor)."""
    try:
        async with get_engine(settings).connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Healthcheck: la base de datos no responde.")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "error", "env": settings.app_env},
        )
    return JSONResponse({"status": "ok", "db": "ok", "env": settings.app_env})
