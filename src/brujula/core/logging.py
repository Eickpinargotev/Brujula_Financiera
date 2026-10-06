"""Configuración de logging. Reglas: sin secretos ni tokens en los logs."""

from __future__ import annotations

import logging


def configure_logging(app_env: str = "development") -> None:
    """Configura el logging global según el entorno, evitando fugas de secretos."""
    level = logging.INFO if app_env == "production" else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Evita ruido y posibles datos sensibles de solicitudes externas.
    for noisy in ("httpx", "httpcore", "aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
