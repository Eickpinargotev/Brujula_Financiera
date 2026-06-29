"""Utilidades de fecha con zona horaria (por defecto America/Guayaquil)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/Guayaquil"


def today(tz: str = DEFAULT_TZ) -> date:
    """Fecha de hoy en la zona horaria indicada (evita desfases por UTC)."""
    return datetime.now(ZoneInfo(tz)).date()
