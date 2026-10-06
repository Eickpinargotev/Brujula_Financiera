"""Registro del dashboard en la app FastAPI.

Monta /static, las páginas (login/logout/dashboard) y la API de datos. Diseño ligero:
Jinja2 + CSS propio (tema oscuro neutro) + ECharts vendorizado (offline) + JS vanilla
que re-renderiza al instante tras cada cambio. Ver docs/finance-model.md §5.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from brujula.config.settings import Settings
from brujula.web.routes import api, pages
from brujula.web.templating import BASE_DIR, templates


class _StaticVersion:
    """Versión de los estáticos para cache-busting (`?v=…`).

    Producción: sello del arranque (una imagen = una versión).
    Desarrollo: mtime más reciente de `static/`, así editar CSS/JS se ve al recargar
    sin reiniciar el contenedor (uvicorn --reload solo vigila los .py).
    """

    def __init__(self, static_dir: Path, produccion: bool) -> None:
        self._dir = static_dir
        self._fijo = str(int(time.time())) if produccion else None

    def __str__(self) -> str:
        if self._fijo is not None:
            return self._fijo
        try:
            mtimes = (f.stat().st_mtime for f in self._dir.rglob("*") if f.is_file())
            return str(int(max(mtimes, default=time.time())))
        except OSError:
            return str(int(time.time()))


def register_web(app: FastAPI, settings: Settings) -> None:
    """Monta /static, las rutas del dashboard y la API de datos."""
    static_dir = BASE_DIR / "static"
    templates.env.globals["static_v"] = _StaticVersion(static_dir, settings.is_production)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(pages.router)
    app.include_router(api.router)
