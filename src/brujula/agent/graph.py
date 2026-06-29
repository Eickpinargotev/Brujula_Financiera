"""Grafo del agente (LangGraph).

Flujo por turno:
    decidir (LLM → AgentDecision)
      ├─ registrar y completo      → preparar borrador + PEDIR CONFIRMACIÓN
      ├─ registrar e incompleto    → preguntar el dato que falta (no guarda)
      ├─ confirmar (con pendiente) → persistir en la BD
      ├─ cancelar                  → descartar
      ├─ consultar                 → reporte calculado en Python
      └─ otro                      → respuesta amable
    finalizar (añadir respuesta + podar a 7 interacciones)

La memoria por chat la maneja el checkpointer (thread_id = chat_id) y se poda para no
crecer infinitamente. La persistencia ocurre SOLO tras la confirmación del usuario.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from brujula.agent.llm import Decider, build_decider, build_system_message
from brujula.agent.memory import MAX_INTERACTIONS, window
from brujula.agent.schemas import AgentDecision, Intent
from brujula.config.settings import get_settings
from brujula.db.engine import get_sessionmaker
from brujula.db.repository import add_movimiento
from brujula.domain.dates import today
from brujula.services.reports import resumen_mes

_MAX_MESSAGES = MAX_INTERACTIONS * 2


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    pending: dict[str, Any] | None
    decision: AgentDecision
    reply: str


# --------------------------------------------------------------------------- helpers


def _draft_to_pending(d: AgentDecision) -> dict[str, Any]:
    """Convierte el borrador del LLM en un dict serializable, resolviendo la fecha."""
    if d.intent == Intent.registrar_gasto and d.gasto:
        g = d.gasto
        return {
            "tipo": "gasto",
            "monto": g.monto,
            "sobre": g.sobre.value,
            "categoria": g.categoria.value,
            "descripcion": g.descripcion,
            "comercio": g.comercio,
            "fecha": (g.fecha or today()).isoformat(),
        }
    if d.intent == Intent.registrar_ingreso and d.ingreso:
        i = d.ingreso
        return {
            "tipo": "ingreso",
            "monto": i.monto,
            "fuente_ingreso": i.fuente_ingreso.value,
            "descripcion": i.descripcion,
            "comercio": i.comercio,
            "fecha": (i.fecha or today()).isoformat(),
        }
    return {}


def _confirmation_text(p: dict[str, Any]) -> str:
    if p.get("tipo") == "gasto":
        extra = f", en {p['comercio']}" if p.get("comercio") else ""
        cuerpo = (
            f"un gasto de ${p['monto']:,.2f} — {p['descripcion']} "
            f"(sobre: {p['sobre']}, categoría: {p['categoria']}{extra})"
        )
    else:
        cuerpo = (
            f"un ingreso de ${p['monto']:,.2f} — {p['descripcion']} "
            f"(fuente: {p['fuente_ingreso']})"
        )
    return f"Voy a registrar {cuerpo} con fecha {p['fecha']}. ¿Confirmo?"


def _success_text(p: dict[str, Any]) -> str:
    etiqueta = "gasto" if p.get("tipo") == "gasto" else "ingreso"
    return f"✅ Registrado: {etiqueta} de ${p['monto']:,.2f} — {p['descripcion']}."


def _pending_to_kwargs(p: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "tipo": p["tipo"],
        "monto": p["monto"],
        "fecha": date.fromisoformat(p["fecha"]),
        "descripcion": p["descripcion"],
        "comercio": p.get("comercio"),
    }
    if p["tipo"] == "gasto":
        kwargs["sobre"] = p["sobre"]
        kwargs["categoria"] = p["categoria"]
    else:
        kwargs["fuente_ingreso"] = p["fuente_ingreso"]
    return kwargs


# --------------------------------------------------------------------------- build


SessionFactory = Callable[[], Any]


def build_agent(
    decider: Decider | None = None,
    session_factory: SessionFactory | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Construye el agente compilado. Inyecta `decider`/`session_factory` en tests."""
    settings = get_settings()
    decide_fn: Decider = decider or build_decider(settings)
    sf: SessionFactory = session_factory or get_sessionmaker(settings)
    saver = checkpointer if checkpointer is not None else MemorySaver()

    async def n_decide(state: AgentState) -> dict[str, Any]:
        pending = state.get("pending")
        summary = _confirmation_text(pending) if pending else None
        msgs = window(state["messages"])
        decision = await decide_fn([build_system_message(summary), *msgs])
        return {"decision": decision}

    def route(state: AgentState) -> str:
        d = state["decision"]
        pending = state.get("pending")
        if pending and d.intent == Intent.confirmar:
            return "persist"
        if pending and d.intent == Intent.cancelar:
            return "cancel"
        if d.intent in (Intent.registrar_gasto, Intent.registrar_ingreso):
            draft = d.gasto if d.intent == Intent.registrar_gasto else d.ingreso
            if draft is None or d.faltan_campos or d.necesita_aclaracion:
                return "ask"
            return "stage"
        if d.intent == Intent.consultar:
            return "query"
        return "reply"

    def n_stage(state: AgentState) -> dict[str, Any]:
        pending = _draft_to_pending(state["decision"])
        return {"pending": pending, "reply": _confirmation_text(pending)}

    async def n_persist(state: AgentState) -> dict[str, Any]:
        pending = state["pending"]
        assert pending is not None
        async with sf() as session:
            await add_movimiento(session, **_pending_to_kwargs(pending))
            await session.commit()
        return {"pending": None, "reply": _success_text(pending)}

    def n_cancel(state: AgentState) -> dict[str, Any]:
        return {"pending": None, "reply": "Listo, lo descarté. ¿Algo más?"}

    def n_ask(state: AgentState) -> dict[str, Any]:
        msg = state["decision"].mensaje or "¿Me das ese dato para poder registrarlo?"
        return {"reply": msg}

    async def n_query(state: AgentState) -> dict[str, Any]:
        async with sf() as session:
            texto = await resumen_mes(session, today())
        return {"reply": texto}

    def n_reply(state: AgentState) -> dict[str, Any]:
        return {"reply": state["decision"].mensaje or "¿En qué te ayudo?"}

    def n_finalize(state: AgentState) -> dict[str, Any]:
        reply = state.get("reply", "")
        existing = state["messages"]
        over = max(0, len(existing) + 1 - _MAX_MESSAGES)
        removals = [RemoveMessage(id=existing[i].id) for i in range(over)]
        return {"messages": [AIMessage(content=reply), *removals]}

    g = StateGraph(AgentState)
    g.add_node("decide", n_decide)
    g.add_node("stage", n_stage)
    g.add_node("persist", n_persist)
    g.add_node("cancel", n_cancel)
    g.add_node("ask", n_ask)
    g.add_node("query", n_query)
    g.add_node("reply", n_reply)
    g.add_node("finalize", n_finalize)

    g.add_edge(START, "decide")
    g.add_conditional_edges(
        "decide",
        route,
        {
            "stage": "stage",
            "persist": "persist",
            "cancel": "cancel",
            "ask": "ask",
            "query": "query",
            "reply": "reply",
        },
    )
    for node in ("stage", "persist", "cancel", "ask", "query", "reply"):
        g.add_edge(node, "finalize")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=saver)


async def run_turn(agent: Any, thread_id: str, text: str) -> str:
    """Procesa un mensaje del usuario y devuelve la respuesta del agente."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke({"messages": [HumanMessage(content=text)]}, config)
    return result.get("reply", "")
