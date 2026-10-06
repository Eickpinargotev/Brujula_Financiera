"""Acceso a datos del dashboard.

Las funciones de agregación devuelven estructuras simples (no ORM) ya listas para que
la capa web las componga; la interpretación financiera vive en `domain/`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import case, extract, func, or_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.models import (
    Account,
    AccountAdjustment,
    Envelope,
    Goal,
    GoalCommitment,
    IncomeSource,
    Movimiento,
    Parameter,
    Transfer,
)


def _es_prestamo() -> Any:
    """Expresión SQL para separar préstamos del flujo financiero ordinario."""
    gasto = func.lower(func.coalesce(Movimiento.sobre, ""))
    ingreso = func.lower(func.coalesce(Movimiento.fuente_ingreso, ""))
    return or_(
        gasto.like("prestamo%"),
        gasto.like("préstamo%"),
        ingreso.like("prestamo%"),
        ingreso.like("préstamo%"),
    )


def _no_es_prestamo() -> Any:
    return ~_es_prestamo()


async def add_movimiento(
    session: AsyncSession,
    *,
    tipo: str,
    monto: float,
    fecha: date,
    descripcion: str,
    sobre: str | None = None,
    fuente_ingreso: str | None = None,
    comercio: str | None = None,
    account_id: int | None = None,
    grupo_id: int | None = None,
) -> Movimiento:
    """Inserta un movimiento (gasto o ingreso) y lo devuelve."""
    mov = Movimiento(
        tipo=tipo,
        monto=monto,
        fecha=fecha,
        descripcion=descripcion,
        sobre=sobre,
        fuente_ingreso=fuente_ingreso,
        comercio=comercio,
        account_id=account_id,
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
    sobre: str | None = None,
    fuente: str | None = None,
    account_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Movimiento]:
    """Lista movimientos (recientes primero), filtrables por tipo, clasificación y rango.

    `sobre` filtra la categoría del gasto; `fuente`, la categoría del ingreso.
    """
    stmt = select(Movimiento).order_by(Movimiento.fecha.desc(), Movimiento.id.desc())
    if tipo is not None:
        stmt = stmt.where(Movimiento.tipo == tipo)
    if sobre is not None:
        stmt = stmt.where(Movimiento.sobre == sobre)
    if fuente is not None:
        stmt = stmt.where(Movimiento.fuente_ingreso == fuente)
    if account_id is not None:
        stmt = stmt.where(Movimiento.account_id == account_id)
    if desde is not None:
        stmt = stmt.where(Movimiento.fecha >= desde)
    if hasta is not None:
        stmt = stmt.where(Movimiento.fecha <= hasta)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


async def movimientos_en_rango(
    session: AsyncSession, desde: date, hasta: date, tipo: str | None = None
) -> list[Movimiento]:
    """Todos los movimientos entre dos fechas (orden cronológico), para el reporte."""
    stmt = (
        select(Movimiento)
        .where(Movimiento.fecha >= desde, Movimiento.fecha <= hasta)
        .order_by(Movimiento.fecha, Movimiento.id)
    )
    if tipo is not None:
        stmt = stmt.where(Movimiento.tipo == tipo)
    return list((await session.execute(stmt)).scalars().all())


async def todos_movimientos_cronologicos(session: AsyncSession) -> list[Movimiento]:
    """Historial completo en orden estable; base para reconstruir prestamos FIFO."""
    stmt = select(Movimiento).order_by(Movimiento.fecha, Movimiento.id)
    return list((await session.execute(stmt)).scalars().all())


async def eliminar_movimientos(
    session: AsyncSession, desde: date | None = None, hasta: date | None = None
) -> int:
    """Borra movimientos del rango dado (sin rango = TODO el historial). Devuelve cuántos."""
    stmt = sa_delete(Movimiento)
    if desde is not None:
        stmt = stmt.where(Movimiento.fecha >= desde)
    if hasta is not None:
        stmt = stmt.where(Movimiento.fecha <= hasta)
    res = await session.execute(stmt)
    return int(getattr(res, "rowcount", 0) or 0)


async def ultima_fecha(session: AsyncSession) -> date | None:
    """Fecha del movimiento ordinario más reciente (los préstamos van aparte)."""
    return (
        await session.execute(select(func.max(Movimiento.fecha)).where(_no_es_prestamo()))
    ).scalar()


async def dias_con_datos(session: AsyncSession) -> list[tuple[date, int]]:
    """Fechas con movimientos o transferencias, en orden cronológico."""
    movement_rows = (
        await session.execute(
            select(Movimiento.fecha, func.count())
            .group_by(Movimiento.fecha)
            .order_by(Movimiento.fecha)
        )
    ).all()
    transfer_rows = (
        await session.execute(
            select(Transfer.fecha, func.count())
            .group_by(Transfer.fecha)
            .order_by(Transfer.fecha)
        )
    ).all()
    totals: dict[date, int] = {}
    for movement_date, count in [*movement_rows, *transfer_rows]:
        totals[movement_date] = totals.get(movement_date, 0) + int(count or 0)
    return sorted(totals.items())


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
    """Sumas mensuales del flujo ordinario; los préstamos viven por separado."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    rows = (
        await session.execute(
            select(col, Movimiento.tipo, func.sum(Movimiento.monto))
            .where(_no_es_prestamo())
            .group_by(col, Movimiento.tipo)
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
    """(ingreso_total, gasto_total) ordinarios del mes; excluye préstamos."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    rows = (
        await session.execute(
            select(Movimiento.tipo, func.sum(Movimiento.monto))
            .where(col == _periodo(anio, mes), _no_es_prestamo())
            .group_by(Movimiento.tipo)
        )
    ).all()
    d = {tipo: float(v or 0.0) for tipo, v in rows}
    return round(d.get("ingreso", 0.0), 2), round(d.get("gasto", 0.0), 2)


async def totales_rango(session: AsyncSession, desde: date, hasta: date) -> tuple[float, float]:
    """(ingreso_total, gasto_total) ordinarios del rango; excluye préstamos."""
    rows = (
        await session.execute(
            select(Movimiento.tipo, func.sum(Movimiento.monto))
            .where(
                Movimiento.fecha >= desde,
                Movimiento.fecha <= hasta,
                _no_es_prestamo(),
            )
            .group_by(Movimiento.tipo)
        )
    ).all()
    d = {tipo: float(v or 0.0) for tipo, v in rows}
    return round(d.get("ingreso", 0.0), 2), round(d.get("gasto", 0.0), 2)


async def gasto_por_sobre_rango(
    session: AsyncSession, desde: date, hasta: date
) -> dict[str, float]:
    """Gasto agrupado por sobre (categoría) entre dos fechas inclusive."""
    rows = (
        await session.execute(
            select(Movimiento.sobre, func.sum(Movimiento.monto))
            .where(
                Movimiento.tipo == "gasto",
                Movimiento.fecha >= desde,
                Movimiento.fecha <= hasta,
                _no_es_prestamo(),
            )
            .group_by(Movimiento.sobre)
        )
    ).all()
    return {(s or "otros"): round(float(t or 0.0), 2) for s, t in rows}


async def ingreso_por_mes(
    session: AsyncSession, desde: date | None = None, hasta: date | None = None
) -> dict[str, float]:
    """{'2026-06': ingreso_total, ...} en el rango dado (inclusive). Base del arrastre."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    stmt = (
        select(col, func.sum(Movimiento.monto))
        .where(Movimiento.tipo == "ingreso", _no_es_prestamo())
        .group_by(col)
    )
    if desde is not None:
        stmt = stmt.where(Movimiento.fecha >= desde)
    if hasta is not None:
        stmt = stmt.where(Movimiento.fecha <= hasta)
    rows = (await session.execute(stmt)).all()
    return {p: round(float(t or 0.0), 2) for p, t in rows}


async def gasto_por_sobre_por_mes(
    session: AsyncSession, desde: date | None = None, hasta: date | None = None
) -> dict[str, dict[str, float]]:
    """{'2026-06': {'familia': 50.0, ...}, ...} en el rango dado (inclusive)."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    stmt = (
        select(col, Movimiento.sobre, func.sum(Movimiento.monto))
        .where(Movimiento.tipo == "gasto", _no_es_prestamo())
        .group_by(col, Movimiento.sobre)
    )
    if desde is not None:
        stmt = stmt.where(Movimiento.fecha >= desde)
    if hasta is not None:
        stmt = stmt.where(Movimiento.fecha <= hasta)
    rows = (await session.execute(stmt)).all()
    out: dict[str, dict[str, float]] = {}
    for periodo, sobre, total in rows:
        out.setdefault(periodo, {})[sobre or "otros"] = round(float(total or 0.0), 2)
    return out


async def primera_fecha(session: AsyncSession) -> date | None:
    """Fecha del movimiento ordinario más antiguo (los préstamos van aparte)."""
    return (
        await session.execute(select(func.min(Movimiento.fecha)).where(_no_es_prestamo()))
    ).scalar()


async def gasto_por_sobre(session: AsyncSession, anio: int, mes: int) -> dict[str, float]:
    """Gasto del mes agrupado por sobre."""
    col = func.strftime("%Y-%m", Movimiento.fecha)
    rows = (
        await session.execute(
            select(Movimiento.sobre, func.sum(Movimiento.monto))
            .where(
                Movimiento.tipo == "gasto",
                col == _periodo(anio, mes),
                _no_es_prestamo(),
            )
            .group_by(Movimiento.sobre)
        )
    ).all()
    return {(s or "otros"): round(float(t or 0.0), 2) for s, t in rows}


# --- Catálogos / parámetros ---------------------------------------------------------


async def parametros(session: AsyncSession) -> dict[str, str]:
    """Todos los parámetros como diccionario {clave: valor}."""
    rows = (await session.execute(select(Parameter.key, Parameter.value))).all()
    return {k: v for k, v in rows}


async def total_profit(session: AsyncSession) -> float:
    """Ahorro histórico ordinario = Σ ingresos − Σ gastos, sin préstamos."""
    rows = (
        await session.execute(
            select(Movimiento.tipo, func.sum(Movimiento.monto))
            .where(_no_es_prestamo())
            .group_by(Movimiento.tipo)
        )
    ).all()
    d = {tipo: float(v or 0.0) for tipo, v in rows}
    return round(d.get("ingreso", 0.0) - d.get("gasto", 0.0), 2)


# --- Cuentas, conciliaciones y transferencias --------------------------------------


async def listar_cuentas(session: AsyncSession, *, incluir_inactivas: bool = True) -> list[Account]:
    stmt = select(Account).order_by(Account.id)
    if not incluir_inactivas:
        stmt = stmt.where(Account.activa.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def obtener_cuenta(session: AsyncSession, account_id: int) -> Account | None:
    return await session.get(Account, account_id)


async def crear_cuenta(
    session: AsyncSession, *, nombre: str, moneda: str = "USD"
) -> Account:
    account = Account(nombre=nombre, moneda=moneda, activa=True)
    session.add(account)
    await session.flush()
    return account


async def actualizar_cuenta(
    session: AsyncSession, account_id: int, cambios: dict[str, Any]
) -> bool:
    account = await session.get(Account, account_id)
    if account is None:
        return False
    for campo, valor in cambios.items():
        setattr(account, campo, valor)
    await session.flush()
    return True


async def saldos_cuentas(session: AsyncSession) -> list[dict[str, Any]]:
    """Saldo contable de cada cuenta, incluyendo préstamos como flujo de efectivo."""
    accounts = await listar_cuentas(session)
    balances = {a.id: 0.0 for a in accounts}

    movement_rows = (
        await session.execute(
            select(
                Movimiento.account_id,
                func.sum(
                    case(
                        (Movimiento.tipo == "ingreso", Movimiento.monto),
                        else_=-Movimiento.monto,
                    )
                ),
            )
            .where(Movimiento.account_id.is_not(None))
            .group_by(Movimiento.account_id)
        )
    ).all()
    for account_id, total in movement_rows:
        balances[int(account_id)] += float(total or 0.0)

    adjustment_rows = (
        await session.execute(
            select(AccountAdjustment.account_id, func.sum(AccountAdjustment.monto)).group_by(
                AccountAdjustment.account_id
            )
        )
    ).all()
    for account_id, total in adjustment_rows:
        balances[int(account_id)] += float(total or 0.0)

    transfer_rows = (
        await session.execute(
            select(
                Transfer.source_account_id,
                Transfer.destination_account_id,
                Transfer.monto,
            )
        )
    ).all()
    for source_id, destination_id, amount in transfer_rows:
        balances[int(source_id)] -= float(amount)
        balances[int(destination_id)] += float(amount)

    return [
        {
            "id": account.id,
            "nombre": account.nombre,
            "moneda": account.moneda,
            "activa": account.activa,
            "saldo": round(balances[account.id], 2),
        }
        for account in accounts
    ]


async def saldo_total_cuentas(session: AsyncSession) -> float:
    return round(sum(float(c["saldo"]) for c in await saldos_cuentas(session)), 2)


async def conciliar_cuenta(
    session: AsyncSession,
    *,
    account_id: int,
    saldo_real: float,
    fecha: date,
    descripcion: str = "Conciliación de saldo real",
) -> AccountAdjustment | None:
    account = await obtener_cuenta(session, account_id)
    if account is None:
        return None
    current = next(c for c in await saldos_cuentas(session) if c["id"] == account_id)
    delta = round(saldo_real - float(current["saldo"]), 2)
    adjustment = AccountAdjustment(
        account_id=account_id,
        fecha=fecha,
        monto=delta,
        descripcion=descripcion,
    )
    session.add(adjustment)
    await session.flush()
    return adjustment


async def listar_ajustes_cuenta(
    session: AsyncSession, account_id: int
) -> list[AccountAdjustment]:
    stmt = (
        select(AccountAdjustment)
        .where(AccountAdjustment.account_id == account_id)
        .order_by(AccountAdjustment.fecha.desc(), AccountAdjustment.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def contar_usos_cuenta(session: AsyncSession, account_id: int) -> int:
    movimientos = (
        await session.execute(
            select(func.count()).select_from(Movimiento).where(Movimiento.account_id == account_id)
        )
    ).scalar_one()
    ajustes = (
        await session.execute(
            select(func.count())
            .select_from(AccountAdjustment)
            .where(AccountAdjustment.account_id == account_id)
        )
    ).scalar_one()
    transferencias = (
        await session.execute(
            select(func.count())
            .select_from(Transfer)
            .where(
                or_(
                    Transfer.source_account_id == account_id,
                    Transfer.destination_account_id == account_id,
                )
            )
        )
    ).scalar_one()
    return int(movimientos or 0) + int(ajustes or 0) + int(transferencias or 0)


async def listar_transferencias(
    session: AsyncSession,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    account_id: int | None = None,
) -> list[Transfer]:
    stmt = select(Transfer).order_by(Transfer.fecha.desc(), Transfer.id.desc())
    if desde is not None:
        stmt = stmt.where(Transfer.fecha >= desde)
    if hasta is not None:
        stmt = stmt.where(Transfer.fecha <= hasta)
    if account_id is not None:
        stmt = stmt.where(
            or_(
                Transfer.source_account_id == account_id,
                Transfer.destination_account_id == account_id,
            )
        )
    return list((await session.execute(stmt)).scalars().all())


async def crear_transferencia(
    session: AsyncSession,
    *,
    source_account_id: int,
    destination_account_id: int,
    fecha: date,
    monto: float,
    descripcion: str,
) -> Transfer:
    transfer = Transfer(
        source_account_id=source_account_id,
        destination_account_id=destination_account_id,
        fecha=fecha,
        monto=monto,
        descripcion=descripcion,
    )
    session.add(transfer)
    await session.flush()
    return transfer


async def actualizar_transferencia(
    session: AsyncSession, transfer_id: int, cambios: dict[str, Any]
) -> bool:
    transfer = await session.get(Transfer, transfer_id)
    if transfer is None:
        return False
    for campo, valor in cambios.items():
        setattr(transfer, campo, valor)
    await session.flush()
    return True


async def eliminar_transferencia(session: AsyncSession, transfer_id: int) -> bool:
    res = await session.execute(sa_delete(Transfer).where(Transfer.id == transfer_id))
    return bool(getattr(res, "rowcount", 0))


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
    ahorro_mensual: float | None = None,
) -> Goal:
    """Crea una meta nueva y la devuelve."""
    meta = Goal(
        nombre=nombre,
        monto_objetivo=monto_objetivo,
        prioridad=prioridad,
        emoji=emoji,
        edad_objetivo=edad_objetivo,
        fecha_objetivo=fecha_objetivo,
        ahorro_mensual=ahorro_mensual,
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
    """Elimina una meta por id (y su historial de hitos). True si existía."""
    await session.execute(sa_delete(GoalCommitment).where(GoalCommitment.goal_id == meta_id))
    res = await session.execute(sa_delete(Goal).where(Goal.id == meta_id))
    return bool(getattr(res, "rowcount", 0))


async def crear_hito(
    session: AsyncSession,
    *,
    goal_id: int,
    fecha: date,
    ahorro_mensual: float,
    ahorrado: float,
    meses_estimados: int | None,
    fecha_estimada: date | None,
) -> GoalCommitment:
    """Registra un hito del compromiso de ahorro de una meta (foto del momento)."""
    hito = GoalCommitment(
        goal_id=goal_id,
        fecha=fecha,
        ahorro_mensual=ahorro_mensual,
        ahorrado=ahorrado,
        meses_estimados=meses_estimados,
        fecha_estimada=fecha_estimada,
    )
    session.add(hito)
    await session.flush()
    return hito


async def historial_meta(session: AsyncSession, goal_id: int) -> list[GoalCommitment]:
    """Hitos de compromiso de una meta, del más antiguo al más reciente."""
    stmt = (
        select(GoalCommitment)
        .where(GoalCommitment.goal_id == goal_id)
        .order_by(GoalCommitment.fecha, GoalCommitment.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def listar_sobres(session: AsyncSession) -> list[Envelope]:
    """Sobres/presupuestos configurados (en la UI: **categorías** de gasto)."""
    return list((await session.execute(select(Envelope).order_by(Envelope.id))).scalars().all())


# --- Categorías de gasto (tabla `envelopes`: nombre + tope mensual) ------------------


async def obtener_sobre(session: AsyncSession, sobre_id: int) -> Envelope | None:
    return await session.get(Envelope, sobre_id)


async def crear_sobre(
    session: AsyncSession,
    *,
    nombre: str,
    tipo: str = "fijo",
    valor: float = 0.0,
    arrastre: bool = True,
) -> Envelope:
    """Crea una categoría de gasto (sin tope si `valor` es 0)."""
    env = Envelope(nombre=nombre, tipo=tipo, valor=valor, arrastre=arrastre)
    session.add(env)
    await session.flush()
    return env


async def actualizar_sobre(session: AsyncSession, sobre_id: int, cambios: dict[str, Any]) -> bool:
    """Actualiza los campos dados de una categoría. True si existía."""
    env = await session.get(Envelope, sobre_id)
    if env is None:
        return False
    for campo, valor in cambios.items():
        setattr(env, campo, valor)
    await session.flush()
    return True


async def eliminar_sobre(session: AsyncSession, sobre_id: int) -> bool:
    """Elimina una categoría por id. True si existía."""
    res = await session.execute(sa_delete(Envelope).where(Envelope.id == sobre_id))
    return bool(getattr(res, "rowcount", 0))


async def renombrar_sobre_en_movimientos(session: AsyncSession, viejo: str, nuevo: str) -> int:
    """Reapunta los movimientos de una categoría renombrada. Devuelve cuántos cambió."""
    res = await session.execute(
        sa_update(Movimiento).where(Movimiento.sobre == viejo).values(sobre=nuevo)
    )
    return int(getattr(res, "rowcount", 0) or 0)


async def contar_movimientos_por_sobre(session: AsyncSession, nombre: str) -> int:
    """Cuántos movimientos usan una categoría (para avisar antes de borrarla)."""
    val = (
        await session.execute(
            select(func.count()).select_from(Movimiento).where(Movimiento.sobre == nombre)
        )
    ).scalar()
    return int(val or 0)


# --- Categorías de ingreso (tabla `income_sources`: solo nombre) ---------------------


async def listar_fuentes(session: AsyncSession) -> list[IncomeSource]:
    """Categorías de ingreso configuradas (el dato es `movimientos.fuente_ingreso`)."""
    return list(
        (await session.execute(select(IncomeSource).order_by(IncomeSource.id))).scalars().all()
    )


async def obtener_fuente(session: AsyncSession, fuente_id: int) -> IncomeSource | None:
    return await session.get(IncomeSource, fuente_id)


async def crear_fuente(session: AsyncSession, *, nombre: str) -> IncomeSource:
    """Crea una categoría de ingreso (nombre único)."""
    fuente = IncomeSource(nombre=nombre)
    session.add(fuente)
    await session.flush()
    return fuente


async def actualizar_fuente(
    session: AsyncSession, fuente_id: int, cambios: dict[str, Any]
) -> bool:
    """Actualiza los campos dados de una categoría de ingreso. True si existía."""
    fuente = await session.get(IncomeSource, fuente_id)
    if fuente is None:
        return False
    for campo, valor in cambios.items():
        setattr(fuente, campo, valor)
    await session.flush()
    return True


async def eliminar_fuente(session: AsyncSession, fuente_id: int) -> bool:
    """Elimina una categoría de ingreso por id. True si existía."""
    res = await session.execute(sa_delete(IncomeSource).where(IncomeSource.id == fuente_id))
    return bool(getattr(res, "rowcount", 0))


async def renombrar_fuente_en_movimientos(session: AsyncSession, viejo: str, nuevo: str) -> int:
    """Reapunta los ingresos de una fuente renombrada. Devuelve cuántos cambió."""
    res = await session.execute(
        sa_update(Movimiento)
        .where(Movimiento.fuente_ingreso == viejo)
        .values(fuente_ingreso=nuevo)
    )
    return int(getattr(res, "rowcount", 0) or 0)


async def contar_movimientos_por_fuente(session: AsyncSession, nombre: str) -> int:
    """Cuántos ingresos usan una fuente (para avisar antes de borrarla)."""
    val = (
        await session.execute(
            select(func.count())
            .select_from(Movimiento)
            .where(Movimiento.fuente_ingreso == nombre)
        )
    ).scalar()
    return int(val or 0)


# --- Parámetros (edición desde Configuración) ---------------------------------------


async def guardar_parametros(session: AsyncSession, valores: dict[str, str]) -> None:
    """Inserta o actualiza parámetros clave-valor."""
    for key, value in valores.items():
        param = await session.get(Parameter, key)
        if param is None:
            session.add(Parameter(key=key, value=value))
        else:
            param.value = value
    await session.flush()
