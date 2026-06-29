"""Ventana de memoria del agente: solo las últimas N interacciones.

Una "interacción" = un par (mensaje del usuario, respuesta del agente). Mantenemos las
últimas 7 para que la memoria del chat no crezca infinitamente ni queme tokens.
"""

from __future__ import annotations

from collections.abc import Sequence

MAX_INTERACTIONS = 7


def window[T](messages: Sequence[T], max_interactions: int = MAX_INTERACTIONS) -> list[T]:
    """Devuelve solo los últimos `max_interactions` pares de mensajes."""
    keep = max_interactions * 2
    return list(messages[-keep:]) if len(messages) > keep else list(messages)


def overflow[T](messages: Sequence[T], max_interactions: int = MAX_INTERACTIONS) -> list[T]:
    """Devuelve los mensajes que sobran (a eliminar para no crecer infinitamente)."""
    keep = max_interactions * 2
    return list(messages[:-keep]) if len(messages) > keep else []
