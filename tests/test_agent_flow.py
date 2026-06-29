"""Pruebas del flujo del agente con un LLM falso y BD en memoria (sin red)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from brujula.agent.graph import build_agent, run_turn
from brujula.agent.schemas import AgentDecision, GastoDraft, Intent
from brujula.db.engine import create_all
from brujula.db.repository import movimientos_del_mes
from brujula.domain.dates import today


class ScriptedDecider:
    """Decididor falso: devuelve decisiones predefinidas en orden (repite la última)."""

    def __init__(self, decisiones: list[AgentDecision]) -> None:
        self._decisiones = list(decisiones)

    async def __call__(self, messages: list) -> AgentDecision:  # noqa: ARG002
        if len(self._decisiones) > 1:
            return self._decisiones.pop(0)
        return self._decisiones[0]


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    await create_all(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _movimientos(sf: async_sessionmaker) -> list:
    async with sf() as s:
        return await movimientos_del_mes(s, today().year, today().month)


async def test_gasto_incompleto_pregunta_y_no_guarda(session_factory) -> None:
    decider = ScriptedDecider(
        [
            AgentDecision(
                intent=Intent.registrar_gasto, faltan_campos=["monto"], mensaje="¿Cuánto gastaste?"
            )
        ]
    )
    agent = build_agent(
        decider=decider, session_factory=session_factory, checkpointer=MemorySaver()
    )
    reply = await run_turn(agent, "chat", "gasté en un café")
    assert "Cuánto" in reply
    assert await _movimientos(session_factory) == []


async def test_gasto_completo_pide_confirmacion_y_luego_persiste(session_factory) -> None:
    decider = ScriptedDecider(
        [
            AgentDecision(
                intent=Intent.registrar_gasto,
                gasto=GastoDraft(
                    monto=53.90,
                    sobre="pareja",
                    categoria="comida",
                    descripcion="salida con mi pareja",
                ),
            ),
            AgentDecision(intent=Intent.confirmar),
        ]
    )
    agent = build_agent(
        decider=decider, session_factory=session_factory, checkpointer=MemorySaver()
    )

    r1 = await run_turn(agent, "chat", "gasté 53.90 con mi pareja")
    assert "¿Confirmo?" in r1
    assert await _movimientos(session_factory) == []  # aún NO se guardó

    r2 = await run_turn(agent, "chat", "sí, confirmo")
    assert "Registrado" in r2
    movs = await _movimientos(session_factory)
    assert len(movs) == 1
    assert movs[0].sobre == "pareja"
    assert movs[0].monto == 53.90
    assert movs[0].fecha == today()


async def test_consulta_devuelve_reporte(session_factory) -> None:
    decider = ScriptedDecider([AgentDecision(intent=Intent.consultar)])
    agent = build_agent(
        decider=decider, session_factory=session_factory, checkpointer=MemorySaver()
    )
    reply = await run_turn(agent, "chat", "¿cuánto gasté este mes?")
    assert "Gastos" in reply and "Ahorro" in reply


async def test_memoria_no_crece_infinitamente(session_factory) -> None:
    decider = ScriptedDecider([AgentDecision(intent=Intent.otro, mensaje="¡vamos por esas metas!")])
    agent = build_agent(
        decider=decider, session_factory=session_factory, checkpointer=MemorySaver()
    )
    config = {"configurable": {"thread_id": "chat"}}
    for i in range(20):
        await run_turn(agent, "chat", f"mensaje {i}")
    snapshot = await agent.aget_state(config)
    assert len(snapshot.values["messages"]) <= 14  # 7 interacciones * 2
