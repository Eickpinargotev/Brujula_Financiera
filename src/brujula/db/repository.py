"""Acceso a datos para movimientos (único lugar que toca la BD desde el agente)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.models import Movimiento


async def add_movimiento(
    session: AsyncSession,
    *,
    tipo: str,
    monto: float,
    fecha: date,
    descripcion: str,
    sobre: str | None = None,
    categoria: str | None = None,
    fuente_ingreso: str | None = None,
    comercio: str | None = None,
    grupo_id: int | None = None,
) -> Movimiento:
    """Inserta un movimiento (gasto o ingreso) y lo devuelve."""
    mov = Movimiento(
        tipo=tipo,
        monto=monto,
        fecha=fecha,
        descripcion=descripcion,
        sobre=sobre,
        categoria=categoria,
        fuente_ingreso=fuente_ingreso,
        comercio=comercio,
        grupo_id=grupo_id,
    )
    session.add(mov)
    await session.flush()
    return mov


async def movimientos_del_mes(
    session: AsyncSession, anio: int, mes: int, tipo: str | None = None
) -> list[Movimiento]:
    """Devuelve los movimientos de un mes (opcionalmente filtrados por tipo)."""
    stmt = select(Movimiento).where(
        extract("year", Movimiento.fecha) == anio,
        extract("month", Movimiento.fecha) == mes,
    )
    if tipo is not None:
        stmt = stmt.where(Movimiento.tipo == tipo)
    return list((await session.execute(stmt)).scalars().all())
