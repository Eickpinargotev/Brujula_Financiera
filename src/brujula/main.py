"""Entrypoint de Brújula.

Crea la app de FastAPI (dashboard) y, en el `lifespan`, arrancará el bot de Telegram
(polling) como tarea del mismo event loop: **un solo proceso, un solo contenedor**.

Por ahora es un esqueleto que arranca y sirve un placeholder + /health, para validar la
imagen Docker. El cableado del bot y del dashboard se completa en la fase de desarrollo.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from brujula.config.settings import get_settings
from brujula.core.logging import configure_logging
from brujula.db.bootstrap import bootstrap_database

settings = get_settings()
configure_logging(settings.app_env)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Crea las tablas y siembra parámetros/metas/sobres iniciales.
    await bootstrap_database(settings)

    # Arranca el bot de Telegram (polling) SOLO en producción, para no chocar con la nube.
    app.state.bot = None
    if settings.bot_should_poll:
        try:
            from brujula.bot.telegram_bot import start_bot

            app.state.bot = await start_bot(settings)
        except Exception:  # noqa: BLE001 - el dashboard debe seguir vivo
            logger.exception("No se pudo iniciar el bot; el dashboard sigue activo.")
    elif not settings.is_production:
        logger.info("Bot en pausa: en desarrollo no hace polling (evita conflicto con la nube).")
    else:
        logger.warning("Bot no iniciado: faltan TELEGRAM_BOT_TOKEN u OPENAI_API_KEY.")

    yield

    if app.state.bot is not None:
        from brujula.bot.telegram_bot import stop_bot

        await stop_bot(app.state.bot)


# docs/openapi deshabilitados: no exponer el esquema de la API.
app = FastAPI(
    title="Brújula Financiera",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# TODO(desarrollo): montar el dashboard y el login.
#   from brujula.web.app import register_web
#   register_web(app, settings)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def placeholder() -> str:
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Brújula Financiera</title></head><body style='font-family:system-ui;"
        "display:grid;place-items:center;height:100vh;margin:0'>"
        "<div><h1>🧭 Brújula Financiera</h1>"
        "<p>Scaffolding listo. Dashboard en construcción.</p>"
        "</div></body></html>"
    )
