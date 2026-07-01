"""Acceso a datos (único lugar que toca la BD desde el agente y el dashboard).

Las funciones de agregación devuelven estructuras simples (no ORM) ya listas para que
la capa web las componga; la interpretación financiera vive en `domain/`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete as sa_delete
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.models import Envelope, Goal, Movimiento, Parameter


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


async def eliminar_movimiento(session: AsyncSession, mov_id: int) -> bool:
    """Elimina un movimiento por id. True si existía."""
    res = await session.execute(sa_delete(Movimiento).where(Movimiento.id == mov_id))
    return bool(getattr(res, "rowcount", 0))


async def actualizar_movimiento(
    session: AsyncSession, mov_id: int, cambios: dict[str, Any]
) -> bool:
    """Actualiza los campos dados de un movimiento. True si existía."""
    mov = await session.get(Movimiento, mov_id)
    if mov is None:
        return False
    for campo, valor in cambios.items():
        setattr(mov, campo, valor)
    await session.flush()
    return True


async def listar_movimientos(
    session: AsyncSession,
    *,
    tipo: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Movimiento]:
    """Lista movimientos (más recientes primero), opcionalmente filtrados por tipo."""
    stmt = select(Movimiento).order_by(Movimiento.fecha.desc(), Movimiento.id.desc())
    if tipo is not None:
        stmt = stmt.where(Movimiento.tipo == tipo)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


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


# --- Agregados para el dashboard ----------------------------------------------------


def _periodo(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


async def _sumas_por_periodo(session: AsyncSession) -> dict[str, dict[str, float]]:
    """{'2026-06': {'ingreso': .., 'gasto': ..}, ...} sumando por mes y tipo."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    rows = (
        await session.execute(
            select(col, Movimiento.tipo, func.sum(Movimiento.monto)).group_by(col, Movimiento.tipo)
        )
    ).all()
    out: dict[str, dict[str, float]] = {}
    for periodo, tipo, total in rows:
        out.setdefault(periodo, {})[tipo] = float(total or 0.0)
    return out


async def serie_mensual(
    session: AsyncSession, meses: int = 6, hoy: date | None = None
) -> list[dict[str, Any]]:
    """Serie continua de los últimos `meses` (incluye meses sin movimientos en 0)."""
    hoy = hoy or date.today()
    sumas = await _sumas_por_periodo(session)
    inicio = hoy.replace(day=1) - relativedelta(months=meses - 1)
    serie: list[dict[str, Any]] = []
    cur = inicio
    for _ in range(meses):
        periodo = cur.strftime("%Y-%m")
        s = sumas.get(periodo, {})
        ingreso = round(s.get("ingreso", 0.0), 2)
        gasto = round(s.get("gasto", 0.0), 2)
        serie.append(
            {
                "periodo": periodo,
                "ingreso": ingreso,
                "gasto": gasto,
                "ahorro": round(ingreso - gasto, 2),
            }
        )
        cur += relativedelta(months=1)
    return serie


async def totales_mes(session: AsyncSession, anio: int, mes: int) -> tuple[float, float]:
    """(ingreso_total, gasto_total) del mes indicado."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    rows = (
        await session.execute(
            select(Movimiento.tipo, func.sum(Movimiento.monto))
            .where(col == _periodo(anio, mes))
            .group_by(Movimiento.tipo)
        )
    ).all()
    d = {tipo: float(v or 0.0) for tipo, v in rows}
    return round(d.get("ingreso", 0.0), 2), round(d.get("gasto", 0.0), 2)


async def gasto_por_sobre(session: AsyncSession, anio: int, mes: int) -> dict[str, float]:
    """Gasto del mes agrupado por sobre."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    rows = (
        await session.execute(
            select(Movimiento.sobre, func.sum(Movimiento.monto))
            .where(Movimiento.tipo == "gasto", col == _periodo(anio, mes))
            .group_by(Movimiento.sobre)
        )
    ).all()
    return {(s or "otros"): round(float(t or 0.0), 2) for s, t in rows}


async def gasto_por_categoria(session: AsyncSession, anio: int, mes: int) -> dict[str, float]:
    """Gasto del mes agrupado por categoría."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    rows = (
        await session.execute(
            select(Movimiento.categoria, func.sum(Movimiento.monto))
            .where(Movimiento.tipo == "gasto", col == _periodo(anio, mes))
            .group_by(Movimiento.categoria)
        )
    ).all()
    return {(c or "otros"): round(float(t or 0.0), 2) for c, t in rows}


# --- Catálogos / parámetros ---------------------------------------------------------


async def parametros(session: AsyncSession) -> dict[str, str]:
    """Todos los parámetros como diccionario {clave: valor}."""
    rows = (await session.execute(select(Parameter.key, Parameter.value))).all()
    return {k: v for k, v in rows}


async def total_profit(session: AsyncSession) -> float:
    """Ahorro histórico acumulado = Σ ingresos − Σ gastos (todos los movimientos)."""
    rows = (
        await session.execute(
            select(Movimiento.tipo, func.sum(Movimiento.monto)).group_by(Movimiento.tipo)
        )
    ).all()
    d = {tipo: float(v or 0.0) for tipo, v in rows}
    return round(d.get("ingreso", 0.0) - d.get("gasto", 0.0), 2)


# --- Metas (CRUD, ordenadas por prioridad) ------------------------------------------


async def listar_metas(session: AsyncSession) -> list[Goal]:
    """Metas de ahorro ordenadas por prioridad (1 = primera en la cola)."""
    stmt = select(Goal).order_by(Goal.prioridad, Goal.id)
    return list((await session.execute(stmt)).scalars().all())


async def obtener_meta(session: AsyncSession, meta_id: int) -> Goal | None:
    return await session.get(Goal, meta_id)


async def max_prioridad(session: AsyncSession) -> int:
    """Mayor prioridad actual (para poner una meta nueva al final de la cola)."""
    val = (await session.execute(select(func.max(Goal.prioridad)))).scalar()
    return int(val or 0)


async def crear_meta(
    session: AsyncSession,
    *,
    nombre: str,
    monto_objetivo: float,
    prioridad: int,
    emoji: str | None = None,
    edad_objetivo: int | None = None,
    fecha_objetivo: date | None = None,
) -> Goal:
    """Crea una meta nueva y la devuelve."""
    meta = Goal(
        nombre=nombre,
        monto_objetivo=monto_objetivo,
        prioridad=prioridad,
        emoji=emoji,
        edad_objetivo=edad_objetivo,
        fecha_objetivo=fecha_objetivo,
    )
    session.add(meta)
    await session.flush()
    return meta


async def actualizar_meta(session: AsyncSession, meta_id: int, cambios: dict[str, Any]) -> bool:
    """Actualiza los campos dados de una meta. True si existía."""
    meta = await session.get(Goal, meta_id)
    if meta is None:
        return False
    for campo, valor in cambios.items():
        setattr(meta, campo, valor)
    await session.flush()
    return True


async def eliminar_meta(session: AsyncSession, meta_id: int) -> bool:
    """Elimina una meta por id. True si existía."""
    res = await session.execute(sa_delete(Goal).where(Goal.id == meta_id))
    return bool(getattr(res, "rowcount", 0))


async def listar_sobres(session: AsyncSession) -> list[Envelope]:
    """Sobres/presupuestos configurados."""
    return list((await session.execute(select(Envelope).order_by(Envelope.id))).scalars().all())
