"""Pruebas de la capa de datos: creación de tablas y siembra inicial (en memoria)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from brujula.db.engine import create_all
from brujula.db.models import Account, Envelope, Goal, Parameter, Recurrente
from brujula.db.seed import seed_if_empty


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Sesión sobre una BD SQLite en memoria compartida (StaticPool)."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    await create_all(engine)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_seed_inserts_goals(session: AsyncSession) -> None:
    created = await seed_if_empty(session)
    await session.commit()
    assert created is True
    goals = (await session.execute(select(Goal))).scalars().all()
    assert {g.nombre for g in goals} == {"carro", "casa"}
    carro = next(g for g in goals if g.nombre == "carro")
    assert carro.monto_objetivo == 27000.0
    assert carro.edad_objetivo == 30


async def test_seed_inserts_envelopes(session: AsyncSession) -> None:
    await seed_if_empty(session)
    await session.commit()
    envs = (await session.execute(select(Envelope))).scalars().all()
    assert {e.nombre for e in envs} == {
        "familia",
        "pareja",
        "personal",
        "iglesia",
        "transporte",
        "ahorro",
        "prestamo",
    }
    personal = next(e for e in envs if e.nombre == "personal")
    assert personal.tipo == "porcentaje"
    assert personal.valor == 0.05


async def test_seed_inserts_recurrentes(session: AsyncSession) -> None:
    await seed_if_empty(session)
    await session.commit()
    recs = (await session.execute(select(Recurrente))).scalars().all()
    assert {r.nombre for r in recs} == {"Shopify"}
    shopify = recs[0]
    assert shopify.iva == 0.15
    assert shopify.isd == 0.05


async def test_seed_parameters(session: AsyncSession) -> None:
    await seed_if_empty(session)
    await session.commit()
    p = (
        await session.execute(select(Parameter).where(Parameter.key == "base_salary"))
    ).scalar_one()
    assert p.value == "1600"


async def test_seed_inserts_accounts(session: AsyncSession) -> None:
    await seed_if_empty(session)
    await session.commit()
    accounts = (await session.execute(select(Account).order_by(Account.id))).scalars().all()
    assert [a.nombre for a in accounts] == [
        "Banco Guayaquil", "Banco Pichincha", "Binance", "UglyCash"
    ]
    assert all(a.moneda == "USD" and a.activa for a in accounts)


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    await seed_if_empty(session)
    await session.commit()
    created_again = await seed_if_empty(session)
    await session.commit()
    assert created_again is False
    count = (await session.execute(select(func.count()).select_from(Goal))).scalar_one()
    assert count == 2
