"""Configuración de logging. A completar en desarrollo.

Reglas: sin secretos ni tokens en los logs; nivel según APP_ENV.
"""

from __future__ import annotations

import logging


def configure_logging(app_env: str = "development") -> None:
    """Configura el logging global según el entorno."""
    level = logging.INFO if app_env == "production" else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
