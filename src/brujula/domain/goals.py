"""Metas de ahorro (carro, casa…) y su progreso. Lógica pura (sin IO).

Modelo en **cascada por prioridad**: el ahorro acumulado (profit) llena la primera meta
por completo antes de pasar a la siguiente. Ver docs/finance-model.md §3.
"""

from __future__ import annotations

import math


def asignar_cascada(pool: float, objetivos: list[float]) -> tuple[list[float], float]:
    """Reparte `pool` en cascada: llena cada objetivo antes de pasar al siguiente.

    `objetivos` viene ya ordenado por prioridad. Devuelve (ahorrado_por_meta, sobrante_libre).
    """
    restante = max(pool, 0.0)
    asignados: list[float] = []
    for objetivo in objetivos:
        a = min(restante, max(objetivo, 0.0))
        asignados.append(round(a, 2))
        restante -= a
    return asignados, round(restante, 2)


def meses_hasta_objetivo(
    pool: float, objetivo_acumulado: float, ahorro_mensual: float
) -> int | None:
    """Meses hasta que el `pool` (creciendo a `ahorro_mensual`) alcance el objetivo acumulado.

    0 si ya se alcanzó; None si no se ahorra nada (no se alcanzaría nunca).
    """
    faltante = objetivo_acumulado - pool
    if faltante <= 0:
        return 0
    if ahorro_mensual <= 0:
        return None
    return math.ceil(faltante / ahorro_mensual)


def eta_cascada(
    pool: float,
    metas: list[tuple[float, float | None]],
    ahorro_promedio: float,
) -> list[int | None]:
    """Meses hasta completar cada meta, en cascada y con compromiso por meta.

    `metas` = [(monto_objetivo, compromiso_mensual | None), …] ya ordenadas por prioridad.
    El compromiso de cada meta manda su ritmo; si es None se usa `ahorro_promedio`.
    La meta i empieza cuando termina la i-1: meses_i = meses_{i-1} + ceil(faltante_i ÷ ritmo_i).
    None cuando el ritmo efectivo es 0 (no se alcanzaría nunca); arrastra a las siguientes.
    """
    asignados, _ = asignar_cascada(pool, [monto for monto, _ in metas])
    out: list[int | None] = []
    acumulado: int | None = 0
    for (monto, compromiso), ahorrado in zip(metas, asignados, strict=True):
        if acumulado is None:
            out.append(None)
            continue
        faltante = max(monto - ahorrado, 0.0)
        if faltante <= 0:
            # En cascada una meta completa siempre va antes que las incompletas.
            out.append(0)
            continue
        ritmo = compromiso if compromiso is not None and compromiso > 0 else ahorro_promedio
        if ritmo <= 0:
            acumulado = None
            out.append(None)
            continue
        acumulado += math.ceil(faltante / ritmo)
        out.append(acumulado)
    return out


def progreso(monto_objetivo: float, ahorrado: float) -> float:
    """Fracción [0, 1] de avance hacia la meta."""
    if monto_objetivo <= 0:
        return 0.0
    return min(max(ahorrado / monto_objetivo, 0.0), 1.0)


def restante(monto_objetivo: float, ahorrado: float) -> float:
    """Cuánto falta para alcanzar la meta (nunca negativo)."""
    return max(monto_objetivo - ahorrado, 0.0)


def ahorro_necesario(restante_meta: float, meses_objetivo: int) -> float:
    """Cuánto hay que ahorrar por mes para llegar a tiempo a la meta."""
    if meses_objetivo <= 0:
        return restante_meta
    return restante_meta / meses_objetivo
