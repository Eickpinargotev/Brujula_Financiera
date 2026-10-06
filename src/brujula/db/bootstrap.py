"""Arranque de la base de datos: migra esquema, crea tablas y siembra valores iniciales."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from uuid import uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from brujula.config.settings import Settings
from brujula.db.engine import create_all, get_engine, get_sessionmaker
from brujula.db.models import Account, AccountAdjustment, Movimiento, Parameter
from brujula.db.safety import backup_database, check_database, database_path
from brujula.db.seed import seed_if_empty

logger = logging.getLogger(__name__)


async def _migrate_goals(engine: AsyncEngine, settings: Settings) -> None:
    """Migración ligera de `goals` al modelo de cascada por prioridad.

    SQLite (single-user, sin Alembic): si la tabla `goals` existe con el esquema viejo
    (sin `prioridad`), se recrea. Los datos de metas son de arranque/derivados, así que
    reconstruirlas es seguro; los movimientos y parámetros NO se tocan.
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql("PRAGMA table_info(goals)")
        cols = [row[1] for row in res.fetchall()]
        if cols and "prioridad" not in cols:
            await conn.exec_driver_sql("DROP TABLE goals")
            logger.info("Migración: tabla 'goals' recreada al modelo de cascada por prioridad.")


async def _table_columns(conn: AsyncConnection, table: str) -> list[str]:
    res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    return [row[1] for row in res.fetchall()]


async def _migrate_drop_categoria(engine: AsyncEngine) -> None:
    """Elimina la columna `categoria`: el `sobre` es la única clasificación del gasto."""
    async with engine.begin() as conn:
        for table in ("movimientos", "recurrentes"):
            cols = await _table_columns(conn, table)
            if "categoria" in cols:
                await conn.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN categoria")
                logger.info("Migración: columna 'categoria' eliminada de '%s'.", table)


async def _migrate_goal_commitment_fields(engine: AsyncEngine) -> None:
    """Añade a `goals` el compromiso mensual y la fecha de creación (si faltan)."""
    async with engine.begin() as conn:
        cols = await _table_columns(conn, "goals")
        if not cols:
            return  # tabla nueva: create_all la crea completa
        if "ahorro_mensual" not in cols:
            await conn.exec_driver_sql("ALTER TABLE goals ADD COLUMN ahorro_mensual FLOAT")
            logger.info("Migración: columna 'ahorro_mensual' añadida a 'goals'.")
        if "creada_en" not in cols:
            # SQLite no acepta default no constante en ADD COLUMN: se rellena aparte.
            await conn.exec_driver_sql("ALTER TABLE goals ADD COLUMN creada_en DATETIME")
            await conn.exec_driver_sql(
                "UPDATE goals SET creada_en = CURRENT_TIMESTAMP WHERE creada_en IS NULL"
            )
            logger.info("Migración: columna 'creada_en' añadida a 'goals'.")


async def _migrate_account_id(engine: AsyncEngine) -> None:
    """Añade la cuenta a movimientos de bases existentes; create_all cubre bases nuevas."""
    async with engine.begin() as conn:
        cols = await _table_columns(conn, "movimientos")
        if cols and "account_id" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE movimientos ADD COLUMN account_id INTEGER REFERENCES accounts(id)"
            )
            await conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_movimientos_account_id "
                "ON movimientos (account_id)"
            )
            logger.info("Migración: columna 'account_id' añadida a 'movimientos'.")


async def _migrate_account_balances(session: AsyncSession) -> bool:
    """Asigna el histórico a Guayaquil y ancla los saldos reales una sola vez."""
    marker = await session.get(Parameter, "accounts_v1_migrated")
    if marker is not None:
        return False

    legacy_count = (await session.execute(
        select(func.count()).select_from(Movimiento).where(Movimiento.account_id.is_(None))
    )).scalar_one()
    if not legacy_count:
        session.add(Parameter(key="accounts_v1_migrated", value="1",
                              description="Cuentas inicializadas sin saldos inventados"))
        return False

    accounts = {
        a.nombre: a
        for a in (await session.execute(select(Account))).scalars().all()
    }
    guayaquil = accounts["Banco Guayaquil"]
    await session.execute(
        update(Movimiento)
        .where(Movimiento.account_id.is_(None))
        .values(account_id=guayaquil.id)
    )
    await session.flush()

    targets = {
        "Banco Guayaquil": 1766.81,
        "Banco Pichincha": 0.79,
        "Binance": 270.02,
        "UglyCash": 41.73,
    }
    for nombre, target in targets.items():
        account = accounts[nombre]
        movement_balance = float(
            (
                await session.execute(
                    select(
                        func.coalesce(
                            func.sum(
                                case(
                                    (Movimiento.tipo == "ingreso", Movimiento.monto),
                                    else_=-Movimiento.monto,
                                )
                            ),
                            0.0,
                        )
                    ).where(Movimiento.account_id == account.id)
                )
            ).scalar_one()
        )
        delta = round(target - movement_balance, 2)
        if abs(delta) >= 0.005:
            session.add(
                AccountAdjustment(
                    account_id=account.id,
                    fecha=date(2026, 9, 11),
                    monto=delta,
                    descripcion="Conciliación inicial de saldos reales",
                )
            )
    session.add(
        Parameter(
            key="accounts_v1_migrated",
            value="1",
            description="Migración inicial de cuentas y conciliación aplicada",
        )
    )
    return True


async def bootstrap_database(settings: Settings) -> None:
    """Migra el esquema, crea las tablas y siembra parámetros/metas/sobres iniciales."""
    path = database_path(settings.database_url)
    if path.exists():
        await asyncio.to_thread(check_database, path)
        await asyncio.to_thread(backup_database, path, "before-startup")
    elif not settings.allow_database_create:
        await asyncio.to_thread(check_database, path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Base de datos activa: %s", path)
    engine = get_engine(settings)
    await _migrate_goals(engine, settings)
    await _migrate_drop_categoria(engine)
    await _migrate_goal_commitment_fields(engine)
    await create_all(engine)
    await _migrate_account_id(engine)

    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session:
        seeded = await seed_if_empty(session)
        # El dashboard real nunca introduce movimientos de demostración al arrancar.
        if await session.get(Parameter, "database_identity") is None:
            session.add(Parameter(key="database_identity", value=str(uuid4()),
                                  description="Identidad persistente de la base activa"))
        accounts_migrated = await _migrate_account_balances(session)
        await session.commit()

    if seeded:
        logger.info("Base de datos sembrada con parámetros, metas y sobres iniciales.")
    else:
        logger.info("Base de datos ya inicializada; nada que sembrar.")
    if accounts_migrated:
        logger.info("Cuentas migradas y saldos iniciales conciliados.")
