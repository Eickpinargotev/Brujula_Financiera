"""Decididor LLM: convierte el historial en un `AgentDecision` estructurado.

Usa GPT-4o-mini con `with_structured_output` (salida validada por Pydantic) y temperatura
0 para determinismo. Política de reintentos acotada para no quemar tokens: ante un fallo
de formato, reintenta pocas veces y, si no lo logra, degrada a una decisión segura.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path

from langchain_core.messages import AnyMessage, SystemMessage

from brujula.agent.schemas import AgentDecision, Intent
from brujula.config.settings import Settings

logger = logging.getLogger(__name__)

# Una función que, dado el historial (incluido el system), devuelve la decisión.
Decider = Callable[[list[AnyMessage]], Awaitable[AgentDecision]]

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
_MAX_RETRIES = 2


@lru_cache
def _base_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_system_message(pending_summary: str | None = None) -> SystemMessage:
    """System message; si hay un movimiento pendiente, añade el contexto de confirmación."""
    text = _base_system_prompt()
    if pending_summary:
        text += (
            "\n\n## Estado actual\n"
            f"Hay un movimiento PENDIENTE de confirmación: {pending_summary}\n"
            "Si el usuario confirma → intent=confirmar. Si lo rechaza → intent=cancelar. "
            "Si lo corrige → un nuevo registrar_* con los datos corregidos."
        )
    return SystemMessage(content=text)


def build_decider(settings: Settings) -> Decider:
    """Crea el decididor real basado en OpenAI (GPT-4o-mini)."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    structured = llm.with_structured_output(AgentDecision)

    async def decide(messages: list[AnyMessage]) -> AgentDecision:
        last_error: Exception | None = None
        for intento in range(_MAX_RETRIES + 1):
            try:
                return await structured.ainvoke(messages)
            except Exception as exc:  # noqa: BLE001 - degradamos con seguridad
                last_error = exc
                logger.warning("Fallo de extracción del LLM (intento %s): %s", intento + 1, exc)
        logger.error("Extracción fallida tras reintentos: %s", last_error)
        return AgentDecision(
            intent=Intent.otro,
            mensaje="No te entendí bien, ¿puedes repetirlo de otra forma?",
        )

    return decide
