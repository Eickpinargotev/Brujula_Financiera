"""Reportes financieros calculados en Python."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.repository import movimientos_del_mes

_MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


async def resumen_mes(session: AsyncSession, hoy: date) -> str:
    """Resumen del mes en curso: ingresos, gastos por sobre y ahorro estimado."""
    movs = await movimientos_del_mes(session, hoy.year, hoy.month)

    ingresos = sum(m.monto for m in movs if m.tipo == "ingreso")
    gastos = sum(m.monto for m in movs if m.tipo == "gasto")
    por_sobre: dict[str, float] = defaultdict(float)
    for m in movs:
        if m.tipo == "gasto":
            por_sobre[m.sobre or "otros"] += m.monto

    ahorro = ingresos - gastos
    lineas = [f"📊 {_MESES[hoy.month - 1].capitalize()} {hoy.year}"]
    lineas.append(f"Ingresos: ${ingresos:,.2f}")
    lineas.append(f"Gastos: ${gastos:,.2f}")
    if por_sobre:
        lineas.append("Por sobre:")
        for sobre, total in sorted(por_sobre.items(), key=lambda kv: -kv[1]):
            lineas.append(f"  · {sobre}: ${total:,.2f}")
    lineas.append(f"Ahorro del mes: ${ahorro:,.2f}")
    return "\n".join(lineas)
