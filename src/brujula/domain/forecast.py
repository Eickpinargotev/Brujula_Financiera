"""Proyecciones y simulador "¿y si subo mis ingresos?". Lógica pura (sin IO).

Ver docs/finance-model.md §3 y §4.
    fecha_proyectada = hoy + ceil(restante / ahorro_actual) meses
    nueva_fecha      = hoy + ceil(restante / (ahorro_actual + delta)) meses
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta


def meses_entre(desde: date, hasta: date) -> int:
    """Número de meses (redondeando hacia arriba los días sueltos) entre dos fechas."""
    rd = relativedelta(hasta, desde)
    meses = rd.years * 12 + rd.months + (1 if rd.days > 0 else 0)
    return max(int(meses), 0)


def edad_en(birth_date: date, fecha: date) -> tuple[int, int]:
    """Edad (años, meses) que se tendrá en `fecha`."""
    rd = relativedelta(fecha, birth_date)
    return rd.years, rd.months


def fecha_proyectada(restante_meta: float, ahorro_mensual: float, hoy: date) -> date | None:
    """Fecha estimada para alcanzar la meta al ritmo de ahorro actual.

    Devuelve None si no se ahorra nada (la meta no se alcanzaría nunca a ese ritmo).
    """
    if ahorro_mensual <= 0 or restante_meta <= 0:
        return hoy if restante_meta <= 0 else None
    meses = math.ceil(restante_meta / ahorro_mensual)
    proyectada: date = hoy + relativedelta(months=meses)
    return proyectada


def meses_para_meta(restante_meta: float, ahorro_mensual: float) -> int | None:
    """Meses necesarios para alcanzar la meta al ritmo dado (None si ahorro ≤ 0)."""
    if restante_meta <= 0:
        return 0
    if ahorro_mensual <= 0:
        return None
    return math.ceil(restante_meta / ahorro_mensual)


def simular_aumento(
    restante_meta: float, ahorro_actual: float, delta: float, hoy: date
) -> dict[str, Any]:
    """Compara la fecha proyectada actual con un aumento `delta` de ahorro mensual.

    Devuelve fechas y los meses que se adelantaría la meta.
    """
    base = fecha_proyectada(restante_meta, ahorro_actual, hoy)
    nueva = fecha_proyectada(restante_meta, ahorro_actual + delta, hoy)
    meses_ahorrados: int | None = None
    if base is not None and nueva is not None:
        meses_ahorrados = max(meses_entre(nueva, base), 0)
    return {
        "fecha_actual": base,
        "fecha_nueva": nueva,
        "meses_ahorrados": meses_ahorrados,
    }


def proyeccion_saldo(saldo_actual: float, ahorro_mensual: float, meses: int) -> list[float]:
    """Saldo proyectado mes a mes (incluye el mes 0 = saldo actual)."""
    return [round(saldo_actual + ahorro_mensual * i, 2) for i in range(meses + 1)]
