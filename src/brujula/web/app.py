"""Registro del dashboard en la app FastAPI.

Monta /static, las páginas (login/logout/dashboard) y la API de datos. Diseño ligero:
Jinja2 + CSS propio (tema futurista glass) + ECharts vendorizado (offline) + JS vanilla
que re-renderiza al instante tras cada cambio. Ver docs/finance-model.md §5.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from brujula.config.settings import Settings
from brujula.web.routes import api, pages
from brujula.web.templating import BASE_DIR


def register_web(app: FastAPI, settings: Settings) -> None:
    """Monta /static, las rutas del dashboard y la API de datos."""
    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "static")),
        name="static",
    )
    app.include_router(pages.router)
    app.include_router(api.router)
