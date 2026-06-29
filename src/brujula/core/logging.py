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

    # httpx/httpcore registran la URL completa de la API de Telegram, que incluye el
    # TOKEN del bot. Los subimos a WARNING para que el token nunca aparezca en los logs.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # python-telegram-bot en DEBUG es muy verboso; lo dejamos en INFO.
    logging.getLogger("telegram").setLevel(logging.INFO)
