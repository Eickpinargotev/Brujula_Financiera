"""Arranque de la base de datos: migra esquema, crea tablas y siembra valores iniciales."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from brujula.config.settings import Settings
from brujula.db.engine import create_all, get_engine, get_sessionmaker
from brujula.db.seed import seed_if_empty
from brujula.db.seed_demo import seed_demo_if_needed

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
            # El demo ya sembrado no vuelve a correr; ajustamos el saldo inicial aquí.
            if not settings.is_production:
                await conn.exec_driver_sql(
                    "UPDATE parameters SET value='6000' WHERE key='saldo_inicial' AND value='0'"
                )


async def bootstrap_database(settings: Settings) -> None:
    """Migra el esquema, crea las tablas y siembra parámetros/metas/sobres iniciales."""
    engine = get_engine(settings)
    await _migrate_goals(engine, settings)
    await create_all(engine)

    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session:
        seeded = await seed_if_empty(session)
        # Datos de ejemplo SOLO en desarrollo (nunca en la nube).
        demo = False
        if not settings.is_production:
            demo = await seed_demo_if_needed(session)
        await session.commit()

    if seeded:
        logger.info("Base de datos sembrada con parámetros, metas y sobres iniciales.")
    else:
        logger.info("Base de datos ya inicializada; nada que sembrar.")
    if demo:
        logger.info("Datos de ejemplo sembrados (solo desarrollo).")
