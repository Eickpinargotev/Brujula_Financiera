"""Arranque de la base de datos: crea tablas y siembra valores iniciales."""

from __future__ import annotations

import logging

from brujula.config.settings import Settings
from brujula.db.engine import create_all, get_engine, get_sessionmaker
from brujula.db.seed import seed_if_empty

logger = logging.getLogger(__name__)


async def bootstrap_database(settings: Settings) -> None:
    """Crea las tablas (si no existen) y siembra parámetros/metas/sobres iniciales."""
    engine = get_engine(settings)
    await create_all(engine)

    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session:
        seeded = await seed_if_empty(session)
        await session.commit()

    if seeded:
        logger.info("Base de datos sembrada con parámetros, metas y sobres iniciales.")
    else:
        logger.info("Base de datos ya inicializada; nada que sembrar.")
